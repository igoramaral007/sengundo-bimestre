import math
import os
import json
import secrets
import sqlite3
import uuid
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash


BASE_DIR  = Path(__file__).resolve().parent
MAX_PRODUCT_IMAGE_SIZE = 5 * 1024 * 1024
PRODUCT_IMAGE_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
PRODUCT_ILLUSTRATIONS = {
    "HW-RAM-002": "images/products/memory-ddr4.svg",
    "SW-WIN-005": "images/products/windows-pro.svg",
    "SW-M365-004": "images/products/m365.svg",
    "PF-MOUSE-006": "images/products/mouse.svg",
    "HW-CPU-003": "images/products/core-i5.svg",
    "HW-SSD-001": "images/products/ssd-nvme.svg",
}
ALLOWED_ITEM_TYPES = {"Hardware", "Software", "Periférico"}
ALLOWED_MOVEMENTS = {"Entrada", "Saída"}
ALLOWED_PAYMENTS = {"PIX", "CARTAO_CREDITO", "BOLETO_FATURADO"}
CENT = Decimal("0.01")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "techstock-manager-dev-key"),
        DATABASE=os.environ.get("DATABASE_PATH", str(BASE_DIR / "techstock.db")),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.update(test_config)

    @app.template_filter("brl")
    def format_brl(value):
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
        formatted = f"{amount:,.2f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"], timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            if _error is not None:
                db.rollback()
            db.close()

    @app.errorhandler(413)
    def request_too_large(error):
        if error.code == 413:
            flash("O envio excedeu o limite permitido. Imagens podem ter até 5 MB.", "error")
            return redirect(url_for("showroom"))
        return error

    def initialize_database():
        db = get_db()
        has_tables = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'products'"
        ).fetchone()
        if not has_tables:
            db.executescript((BASE_DIR / "database.sql").read_text(encoding="utf-8"))
        db.executescript((BASE_DIR / "migration_v2.sql").read_text(encoding="utf-8"))
        product_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(products)")
        }
        if "image_data" not in product_columns:
            db.execute("ALTER TABLE products ADD COLUMN image_data BLOB")
        if "image_mime_type" not in product_columns:
            db.execute(
                """
                ALTER TABLE products ADD COLUMN image_mime_type TEXT
                CHECK (image_mime_type IS NULL OR image_mime_type IN
                    ('image/jpeg', 'image/png', 'image/webp'))
                """
            )
        db.commit()

    with app.app_context():
        initialize_database()

    def normalize_product_image(upload):
        if upload is None or not upload.filename:
            return None
        image_bytes = upload.stream.read(MAX_PRODUCT_IMAGE_SIZE + 1)
        if len(image_bytes) > MAX_PRODUCT_IMAGE_SIZE:
            raise ValueError("A imagem deve ter no máximo 5 MB.")
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image_format = image.format
                if image_format not in PRODUCT_IMAGE_MIME_TYPES:
                    raise ValueError("Use uma imagem nos formatos JPG, PNG ou WebP.")
                if image.width * image.height > 20_000_000:
                    raise ValueError("A imagem é grande demais. Reduza suas dimensões.")
                image.verify()

            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((1600, 1200))
                if image_format == "JPEG" and image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                output = BytesIO()
                save_options = {"optimize": True}
                if image_format in ("JPEG", "WEBP"):
                    save_options["quality"] = 85
                image.save(output, format=image_format, **save_options)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Não foi possível ler a imagem. Selecione um arquivo válido.") from exc
        return output.getvalue(), PRODUCT_IMAGE_MIME_TYPES[image_format]

    def login_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if g.get("current_user") is None:
                flash("Entre com sua conta para acessar o sistema.", "error")
                return redirect(url_for("login", next=request.full_path))
            return view(*args, **kwargs)

        return wrapped_view

    def roles_required(*roles):
        def decorate(view):
            @wraps(view)
            def wrapped_view(*args, **kwargs):
                if g.get("current_user") is None:
                    flash("Entre com sua conta para acessar o sistema.", "error")
                    return redirect(url_for("login", next=request.full_path))
                if g.current_user["perfil_acesso"] not in roles:
                    abort(403)
                return view(*args, **kwargs)

            return wrapped_view

        return decorate

    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        g.current_user = None
        if user_id is not None:
            user = get_db().execute(
                """
                SELECT id, nome_completo, email, perfil_acesso
                FROM usuarios
                WHERE id = ? AND status = 'ATIVO'
                """,
                (user_id,),
            ).fetchone()
            if user is None:
                session.clear()
            else:
                g.current_user = user

    @app.context_processor
    def inject_current_user():
        return {"current_user": g.get("current_user")}

    @app.get("/login")
    def login():
        if g.current_user is not None:
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/login")
    def authenticate():
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            """
            SELECT id, senha_hash, status
            FROM usuarios
            WHERE email = ? COLLATE NOCASE
            """,
            (email,),
        ).fetchone()
        if user is None or user["status"] != "ATIVO" or not check_password_hash(
            user["senha_hash"], password
        ):
            flash("E-mail ou senha inválidos, ou usuário inativo.", "error")
            return render_template("login.html", email=email), 401

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        next_url = request.form.get("next", "")
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("dashboard"))

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("Sessão encerrada.", "success")
        return redirect(url_for("login"))

    def get_catalog_options():
        db = get_db()
        categories = db.execute(
            "SELECT id, name FROM categories ORDER BY name"
        ).fetchall()
        suppliers = db.execute(
            "SELECT id, company_name FROM suppliers ORDER BY company_name"
        ).fetchall()
        return categories, suppliers

    @app.get("/")
    @login_required
    def dashboard():
        db = get_db()
        products = db.execute(
            """
            SELECT p.id, p.sku, p.name, p.manufacturer, p.item_type,
                   p.price, p.stock, p.min_stock, p.location, p.licensing_model,
                   c.name AS category_name, s.company_name AS supplier_name
            FROM products AS p
            INNER JOIN categories AS c ON c.id = p.category_id
            INNER JOIN suppliers AS s ON s.id = p.supplier_id
            WHERE p.active = 1
            ORDER BY CASE WHEN p.stock <= p.min_stock THEN 0 ELSE 1 END,
                     p.name
            """
        ).fetchall()
        stats = db.execute(
            """
            SELECT COUNT(*) AS product_count,
                   COALESCE(SUM(stock), 0) AS unit_count,
                   COALESCE(SUM(CASE WHEN stock <= min_stock THEN 1 ELSE 0 END), 0)
                       AS alert_count
            FROM products
            WHERE active = 1
            """
        ).fetchone()
        movements = db.execute(
            """
            SELECT m.operation, m.quantity, m.created_at, m.note, p.name, p.sku
            FROM movements AS m
            INNER JOIN products AS p ON p.id = m.product_id
            ORDER BY m.id DESC
            LIMIT 6
            """
        ).fetchall()
        return render_template(
            "dashboard.html",
            products=products,
            stats=stats,
            movements=movements,
            recent_sales=db.execute(
                """
                SELECT id, numero_pedido, cliente_nome, valor_total, data_hora
                FROM vendas
                WHERE status_venda = 'CONCLUIDA'
                  AND (? = 'GERENTE' OR usuario_id = ?)
                ORDER BY id DESC LIMIT 5
                """,
                (g.current_user["perfil_acesso"], g.current_user["id"]),
            ).fetchall(),
        )

    @app.route("/products/new", methods=["GET", "POST"])
    @roles_required("GERENTE")
    def new_product():
        categories, suppliers = get_catalog_options()
        if request.method == "POST":
            form = request.form
            sku = form.get("sku", "").strip()
            name = form.get("name", "").strip()
            manufacturer = form.get("manufacturer", "").strip()
            item_type = form.get("item_type", "").strip()
            specification = form.get("specification", "").strip()
            licensing_model = form.get("licensing_model", "").strip()
            location = form.get("location", "").strip()
            try:
                product_image = normalize_product_image(request.files.get("image"))
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template(
                    "product_form.html",
                    categories=categories,
                    suppliers=suppliers,
                    form=form,
                )
            try:
                price = float(form.get("price", ""))
                stock = int(form.get("stock", ""))
                min_stock = int(form.get("min_stock", ""))
                category_id = int(form.get("category_id", ""))
                supplier_id = int(form.get("supplier_id", ""))
            except (TypeError, ValueError):
                flash("Preencha preço, saldo, estoque mínimo, categoria e fornecedor corretamente.", "error")
                return render_template(
                    "product_form.html",
                    categories=categories,
                    suppliers=suppliers,
                    form=form,
                )

            if not all((sku, name, manufacturer, specification, location)):
                flash("Preencha todos os campos obrigatórios do produto.", "error")
            elif item_type not in ALLOWED_ITEM_TYPES:
                flash("Selecione uma classificação válida para o ativo.", "error")
            elif not math.isfinite(price) or price <= 0 or stock < 0 or min_stock < 0:
                flash("O preço deve ser maior que zero e os saldos não podem ser negativos.", "error")
            elif item_type == "Software" and not licensing_model:
                flash("Informe a modalidade de licenciamento do software.", "error")
            else:
                try:
                    db = get_db()
                    cursor = db.execute(
                        """
                        INSERT INTO products
                            (sku, name, manufacturer, item_type, specification,
                             licensing_model, price, stock, min_stock, location,
                             category_id, supplier_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sku,
                            name,
                            manufacturer,
                            item_type,
                            specification,
                            licensing_model or None,
                            price,
                            stock,
                            min_stock,
                            location,
                            category_id,
                            supplier_id,
                        ),
                    )
                    if product_image:
                        db.execute(
                            "UPDATE products SET image_data = ?, image_mime_type = ? WHERE id = ?",
                            (product_image[0], product_image[1], cursor.lastrowid),
                        )
                    db.commit()
                    flash("Ativo cadastrado com sucesso.", "success")
                    return redirect(url_for("dashboard"))
                except sqlite3.IntegrityError as exc:
                    get_db().rollback()
                    if "products.sku" in str(exc):
                        flash("Este SKU já está cadastrado. Informe um código único.", "error")
                    else:
                        flash("Não foi possível cadastrar o ativo. Confira categoria e fornecedor.", "error")
            return render_template(
                "product_form.html",
                categories=categories,
                suppliers=suppliers,
                form=form,
            )
        return render_template(
            "product_form.html", categories=categories, suppliers=suppliers, form={}
        )

    @app.route("/movements/new", methods=["GET", "POST"])
    @roles_required("GERENTE")
    def new_movement():
        db = get_db()
        products = db.execute(
            """
            SELECT id, sku, name, stock FROM products
            WHERE active = 1 ORDER BY name
            """
        ).fetchall()
        if request.method == "POST":
            form = request.form
            operation = form.get("operation", "")
            note = form.get("note", "").strip()
            try:
                product_id = int(form.get("product_id", ""))
                quantity = int(form.get("quantity", ""))
            except (TypeError, ValueError):
                flash("Selecione um ativo e informe uma quantidade inteira válida.", "error")
                return render_template("movement_form.html", products=products, form=form)
            if operation not in ALLOWED_MOVEMENTS:
                flash("Selecione uma operação válida.", "error")
            elif quantity <= 0:
                flash("A quantidade da movimentação deve ser maior que zero.", "error")
            else:
                try:
                    db.execute("BEGIN IMMEDIATE")
                    product = db.execute(
                        "SELECT id, stock FROM products WHERE id = ? AND active = 1",
                        (product_id,),
                    ).fetchone()
                    if product is None:
                        db.rollback()
                        flash("O ativo selecionado não existe ou está desativado.", "error")
                    elif operation == "Saída" and quantity > product["stock"]:
                        db.rollback()
                        flash(
                            f"Saldo insuficiente. Disponível: {product['stock']} unidade(s); "
                            f"solicitado: {quantity}.",
                            "error",
                        )
                    else:
                        delta = quantity if operation == "Entrada" else -quantity
                        db.execute(
                            "UPDATE products SET stock = stock + ? WHERE id = ?",
                            (delta, product_id),
                        )
                        db.execute(
                            """
                            INSERT INTO movements (operation, quantity, note, product_id)
                            VALUES (?, ?, ?, ?)
                            """,
                            (operation, quantity, note or None, product_id),
                        )
                        db.commit()
                        flash(f"{operation} registrada e saldo atualizado.", "success")
                        return redirect(url_for("dashboard"))
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("A movimentação não pôde ser registrada. Confira os dados informados.", "error")
            return render_template("movement_form.html", products=products, form=form)
        return render_template("movement_form.html", products=products, form={})

    @app.route("/catalogs", methods=["GET", "POST"])
    @login_required
    def catalogs():
        db = get_db()
        if request.method == "POST":
            if g.current_user["perfil_acesso"] != "GERENTE":
                abort(403)
            catalog_type = request.form.get("catalog_type", "")
            try:
                if catalog_type == "category":
                    name = request.form.get("name", "").strip()
                    if not name:
                        flash("Informe o nome da categoria.", "error")
                    else:
                        db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                        db.commit()
                        flash("Categoria cadastrada.", "success")
                elif catalog_type == "supplier":
                    company_name = request.form.get("company_name", "").strip()
                    cnpj = request.form.get("cnpj", "").strip()
                    phone = request.form.get("phone", "").strip()
                    email = request.form.get("email", "").strip()
                    if not all((company_name, cnpj, phone, email)):
                        flash("Preencha todos os dados do fornecedor.", "error")
                    else:
                        db.execute(
                            """
                            INSERT INTO suppliers (company_name, cnpj, phone, email)
                            VALUES (?, ?, ?, ?)
                            """,
                            (company_name, cnpj, phone, email),
                        )
                        db.commit()
                        flash("Fornecedor cadastrado.", "success")
                else:
                    flash("Tipo de cadastro inválido.", "error")
            except sqlite3.IntegrityError as exc:
                db.rollback()
                if "categories.name" in str(exc):
                    flash("Já existe uma categoria com esse nome.", "error")
                elif "suppliers.cnpj" in str(exc):
                    flash("Já existe um fornecedor cadastrado com esse CNPJ.", "error")
                else:
                    flash("Não foi possível cadastrar. Confira os dados informados.", "error")
            return redirect(url_for("catalogs"))

        categories = db.execute(
            """
            SELECT c.id, c.name, COUNT(p.id) AS product_count
            FROM categories AS c
            LEFT JOIN products AS p ON p.category_id = c.id
            GROUP BY c.id ORDER BY c.name
            """
        ).fetchall()
        suppliers = db.execute(
            """
            SELECT s.id, s.company_name, s.cnpj, s.phone, s.email,
                   COUNT(p.id) AS product_count
            FROM suppliers AS s
            LEFT JOIN products AS p ON p.supplier_id = s.id
            GROUP BY s.id ORDER BY s.company_name
            """
        ).fetchall()
        return render_template("catalogs.html", categories=categories, suppliers=suppliers)

    @app.get("/showroom")
    def showroom():
        products = get_db().execute(
            """
            SELECT p.id, p.sku, p.name, p.manufacturer, p.item_type,
                   p.specification, p.licensing_model, p.price, p.stock,
                   p.min_stock, c.name AS category_name,
                   (p.image_data IS NOT NULL) AS has_image
            FROM products AS p
            INNER JOIN categories AS c ON c.id = p.category_id
            WHERE p.active = 1
            ORDER BY p.name
            """
        ).fetchall()
        return render_template(
            "showroom.html",
            products=products,
            illustrations=PRODUCT_ILLUSTRATIONS,
        )

    @app.post("/products/<int:product_id>/image")
    @roles_required("GERENTE")
    def update_product_image(product_id):
        upload = request.files.get("image")
        try:
            product_image = normalize_product_image(upload)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("showroom"))
        if product_image is None:
            flash("Selecione uma imagem para o produto.", "error")
            return redirect(url_for("showroom"))

        db = get_db()
        product = db.execute(
            "SELECT id FROM products WHERE id = ? AND active = 1", (product_id,)
        ).fetchone()
        if product is None:
            flash("Produto não encontrado ou descontinuado.", "error")
            return redirect(url_for("showroom"))
        db.execute(
            "UPDATE products SET image_data = ?, image_mime_type = ? WHERE id = ?",
            (product_image[0], product_image[1], product_id),
        )
        db.commit()
        flash("Foto do produto atualizada.", "success")
        return redirect(url_for("showroom"))

    @app.get("/products/<int:product_id>/image")
    def product_image(product_id):
        image = get_db().execute(
            """
            SELECT image_data, image_mime_type
            FROM products
            WHERE id = ? AND active = 1 AND image_data IS NOT NULL
            """,
            (product_id,),
        ).fetchone()
        if image is None:
            abort(404)
        response = app.response_class(
            image["image_data"], mimetype=image["image_mime_type"]
        )
        response.headers["Cache-Control"] = "private, max-age=3600"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/catalogs/delete/<catalog_type>/<int:catalog_id>")
    @roles_required("GERENTE")
    def delete_catalog_entry(catalog_type, catalog_id):
        table = {"category": "categories", "supplier": "suppliers"}.get(catalog_type)
        if table is None:
            flash("Tipo de cadastro inválido.", "error")
            return redirect(url_for("catalogs"))
        db = get_db()
        try:
            cursor = db.execute(f"DELETE FROM {table} WHERE id = ?", (catalog_id,))
            db.commit()
            if cursor.rowcount:
                flash("Cadastro excluído.", "success")
            else:
                flash("O cadastro selecionado não foi encontrado.", "error")
        except sqlite3.IntegrityError:
            db.rollback()
            flash(
                "Não é possível excluir: existem ativos vinculados a este cadastro. "
                "Desative ou reatribua os ativos antes de tentar novamente.",
                "error",
            )
        return redirect(url_for("catalogs"))

    @app.post("/products/<int:product_id>/deactivate")
    @roles_required("GERENTE")
    def deactivate_product(product_id):
        db = get_db()
        cursor = db.execute(
            "UPDATE products SET active = 0 WHERE id = ? AND active = 1",
            (product_id,),
        )
        db.commit()
        if cursor.rowcount:
            flash("Ativo descontinuado. Seu histórico de movimentações foi preservado.", "success")
        else:
            flash("Ativo não encontrado ou já descontinuado.", "error")
        return redirect(url_for("dashboard"))

    @app.post("/products/<int:product_id>/price")
    @roles_required("GERENTE")
    def update_product_price(product_id):
        try:
            price = float(request.form.get("price", ""))
        except (TypeError, ValueError):
            flash("Informe um preço válido.", "error")
            return redirect(url_for("dashboard"))
        if not math.isfinite(price) or price < 0.01:
            flash("O preço base deve ser de pelo menos R$ 0,01.", "error")
            return redirect(url_for("dashboard"))
        price = round(price, 2)
        db = get_db()
        cursor = db.execute(
            "UPDATE products SET price = ? WHERE id = ? AND active = 1",
            (price, product_id),
        )
        db.commit()
        if cursor.rowcount:
            flash("Preço base atualizado. Vendas já concluídas preservam seus valores.", "success")
        else:
            flash("Ativo não encontrado ou já descontinuado.", "error")
        return redirect(url_for("dashboard"))

    @app.get("/sales/new")
    @login_required
    def new_sale():
        products = get_db().execute(
            """
            SELECT p.id, p.sku, p.name, p.manufacturer, p.item_type, p.specification,
                   p.licensing_model, p.price, p.stock,
                   (p.image_data IS NOT NULL) AS has_image
            FROM products AS p
            WHERE p.active = 1 AND p.stock > 0 ORDER BY p.name
            """
        ).fetchall()
        return render_template(
            "checkout.html",
            products=products,
            selected_product_id=request.args.get("produto_id", type=int),
            illustrations=PRODUCT_ILLUSTRATIONS,
        )

    @app.post("/sales")
    @login_required
    def create_sale():
        customer_name = request.form.get("cliente_nome", "").strip()
        customer_document = request.form.get("cliente_documento", "").strip()
        payment_method = request.form.get("forma_pagamento", "")
        raw_items = request.form.get("itens_json", "")

        if not customer_name or not customer_document:
            flash("Informe o nome e o CPF/CNPJ do cliente.", "error")
            return redirect(url_for("new_sale"))
        if payment_method not in ALLOWED_PAYMENTS:
            flash("Selecione uma forma de pagamento válida.", "error")
            return redirect(url_for("new_sale"))
        try:
            submitted_items = json.loads(raw_items)
            if not isinstance(submitted_items, list) or not submitted_items:
                raise ValueError
            quantities = {}
            for item in submitted_items:
                product_id = int(item["produto_id"])
                quantity = int(item["quantidade"])
                if product_id <= 0 or quantity <= 0:
                    raise ValueError
                if quantity > 2_147_483_647:
                    raise ValueError
                quantities[product_id] = quantities.get(product_id, 0) + quantity
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            flash("Adicione produtos válidos ao carrinho antes de confirmar.", "error")
            return redirect(url_for("new_sale"))

        db = get_db()
        order_number = f"TS-{uuid.uuid4().hex[:12].upper()}"
        authenticity_key = secrets.token_urlsafe(32)
        try:
            db.execute("BEGIN IMMEDIATE")
            product_rows = {}
            total = Decimal("0.00")
            for product_id, quantity in quantities.items():
                product = db.execute(
                    """
                    SELECT id, sku, name, item_type, price, stock, active
                    FROM products WHERE id = ?
                    """,
                    (product_id,),
                ).fetchone()
                if product is None or not product["active"]:
                    raise ValueError("Um dos produtos não está mais disponível para venda.")
                price = Decimal(str(product["price"])).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                subtotal = (price * quantity).quantize(CENT)
                total += subtotal
                product_rows[product_id] = (product, quantity, price, subtotal)

            if total <= 0:
                raise ValueError("O total da venda deve ser maior que zero.")

            cursor = db.execute(
                """
                INSERT INTO vendas
                    (numero_pedido, cliente_nome, cliente_documento,
                     forma_pagamento, valor_total, status_venda, usuario_id,
                     chave_autenticidade)
                VALUES (?, ?, ?, ?, ?, 'CONCLUIDA', ?, ?)
                """,
                (
                    order_number,
                    customer_name,
                    customer_document,
                    payment_method,
                    str(total),
                    g.current_user["id"],
                    authenticity_key,
                ),
            )
            sale_id = cursor.lastrowid

            for product_id, (product, quantity, price, subtotal) in product_rows.items():
                debit = db.execute(
                    """
                    UPDATE products SET stock = stock - ?
                    WHERE id = ? AND active = 1 AND stock >= ?
                    """,
                    (quantity, product_id, quantity),
                )
                if debit.rowcount != 1:
                    raise ValueError(
                        f"Saldo insuficiente para {product['name']}. "
                        f"Disponível no momento: {max(product['stock'], 0)}; "
                        f"solicitado: {quantity}."
                    )

                db.execute(
                    """
                    INSERT INTO itens_venda
                        (venda_id, produto_id, quantidade_vendida,
                         preco_unitario_praticado, subtotal_item)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (sale_id, product_id, quantity, str(price), str(subtotal)),
                )
                db.execute(
                    """
                    INSERT INTO movements (operation, quantity, note, product_id)
                    VALUES ('Saída', ?, ?, ?)
                    """,
                    (
                        quantity,
                        f"Venda {order_number} · operador {g.current_user['nome_completo']}",
                        product_id,
                    ),
                )

            db.commit()
        except ValueError as exc:
            db.rollback()
            flash(str(exc), "error")
            return redirect(url_for("new_sale"))
        except sqlite3.Error:
            db.rollback()
            app.logger.exception("Falha ao registrar venda %s", order_number)
            flash(
                "A venda não foi concluída por uma falha no banco. Nenhum item foi baixado.",
                "error",
            )
            return redirect(url_for("new_sale"))

        flash("Venda concluída. Recibo disponível para impressão.", "success")
        return redirect(url_for("sale_detail", sale_id=sale_id))

    def load_sale(sale_id):
        db = get_db()
        sale = db.execute(
            """
            SELECT v.*, u.nome_completo AS operador_nome
            FROM vendas AS v JOIN usuarios AS u ON u.id = v.usuario_id
            WHERE v.id = ?
            """,
            (sale_id,),
        ).fetchone()
        if sale is None:
            abort(404)
        if (
            g.current_user["perfil_acesso"] != "GERENTE"
            and sale["usuario_id"] != g.current_user["id"]
        ):
            abort(403)
        items = db.execute(
            """
            SELECT i.quantidade_vendida, i.preco_unitario_praticado,
                   i.subtotal_item, p.sku, p.name, p.item_type, p.licensing_model
            FROM itens_venda AS i JOIN products AS p ON p.id = i.produto_id
            WHERE i.venda_id = ? ORDER BY i.id
            """,
            (sale_id,),
        ).fetchall()
        return sale, items

    @app.get("/sales/<int:sale_id>")
    @login_required
    def sale_detail(sale_id):
        sale, items = load_sale(sale_id)
        return render_template("sale_receipt.html", sale=sale, items=items)

    @app.get("/sales")
    @roles_required("GERENTE")
    def sales_report():
        sales = get_db().execute(
            """
            SELECT v.id, v.numero_pedido, v.data_hora, v.cliente_nome,
                   v.cliente_documento, v.forma_pagamento, v.valor_total,
                   v.status_venda, u.nome_completo AS operador_nome
            FROM vendas AS v JOIN usuarios AS u ON u.id = v.usuario_id
            ORDER BY v.id DESC
            """
        ).fetchall()
        summary = get_db().execute(
            """
            SELECT COUNT(*) AS sale_count, COALESCE(SUM(valor_total), 0) AS revenue
            FROM vendas WHERE status_venda = 'CONCLUIDA'
            """
        ).fetchone()
        return render_template("sales_report.html", sales=sales, summary=summary)

    @app.post("/sales/<int:sale_id>/cancel")
    @roles_required("GERENTE")
    def cancel_sale(sale_id):
        db = get_db()
        try:
            db.execute("BEGIN IMMEDIATE")
            sale = db.execute(
                "SELECT numero_pedido, status_venda FROM vendas WHERE id = ?",
                (sale_id,),
            ).fetchone()
            if sale is None:
                db.rollback()
                abort(404)
            if sale["status_venda"] != "CONCLUIDA":
                db.rollback()
                flash("Somente vendas concluídas podem ser canceladas.", "error")
                return redirect(url_for("sales_report"))

            items = db.execute(
                """
                SELECT produto_id, quantidade_vendida
                FROM itens_venda WHERE venda_id = ?
                """,
                (sale_id,),
            ).fetchall()
            db.execute(
                "UPDATE vendas SET status_venda = 'CANCELADA' WHERE id = ?",
                (sale_id,),
            )
            for item in items:
                db.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (item["quantidade_vendida"], item["produto_id"]),
                )
                db.execute(
                    """
                    INSERT INTO movements (operation, quantity, note, product_id)
                    VALUES ('Entrada', ?, ?, ?)
                    """,
                    (
                        item["quantidade_vendida"],
                        f"Estorno da venda cancelada {sale['numero_pedido']} "
                        f"· gerente {g.current_user['nome_completo']}",
                        item["produto_id"],
                    ),
                )
            db.commit()
        except sqlite3.Error:
            db.rollback()
            app.logger.exception("Falha ao cancelar venda %s", sale_id)
            flash("Não foi possível cancelar a venda. Nenhuma alteração foi aplicada.", "error")
            return redirect(url_for("sales_report"))

        flash("Venda cancelada e estoque estornado com rastreabilidade.", "success")
        return redirect(url_for("sales_report"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
