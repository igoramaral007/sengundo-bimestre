import sqlite3
import json
import tempfile
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path

from PIL import Image

from app import create_app


class TechStockTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp_dir.name) / "test.db")
        self.app = create_app(
            {"TESTING": True, "DATABASE": self.database, "SECRET_KEY": "test-key"}
        )
        self.client = self.app.test_client()
        self.login_as("gerente@techstore.com", "Gerente123!")

    def tearDown(self):
        self.temp_dir.cleanup()

    def login_as(self, email, password):
        return self.client.post(
            "/login", data={"email": email, "password": password}
        )

    def get_product_id(self, sku):
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
            return row[0]

    def get_product(self, sku):
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            return db.execute(
                "SELECT id, stock FROM products WHERE sku = ?", (sku,)
            ).fetchone()

    def test_database_has_required_seed_data(self):
        with closing(sqlite3.connect(self.database)) as db:
            category_count = db.execute(
                "SELECT COUNT(*) FROM categories"
            ).fetchone()[0]
            supplier_count = db.execute(
                "SELECT COUNT(*) FROM suppliers"
            ).fetchone()[0]
            product_count = db.execute(
                "SELECT COUNT(*) FROM products"
            ).fetchone()[0]
            table_count = db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        self.assertEqual((category_count, supplier_count, product_count), (4, 3, 6))
        self.assertEqual(table_count, 7)

    def test_existing_database_is_upgraded_without_adding_a_table(self):
        legacy_database = Path(self.temp_dir.name) / "legacy.db"
        project_dir = Path(__file__).resolve().parents[1]
        with closing(sqlite3.connect(legacy_database)) as db:
            db.executescript(
                (project_dir / "database.sql").read_text(encoding="utf-8")
            )
            db.executescript(
                (project_dir / "migration_v2.sql").read_text(encoding="utf-8")
            )
            columns_before = {
                row[1] for row in db.execute("PRAGMA table_info(products)")
            }
        self.assertNotIn("image_data", columns_before)

        create_app(
            {"TESTING": True, "DATABASE": str(legacy_database), "SECRET_KEY": "test-key"}
        )
        with closing(sqlite3.connect(legacy_database)) as db:
            columns_after = {row[1] for row in db.execute("PRAGMA table_info(products)")}
            table_count = db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        self.assertIn("image_data", columns_after)
        self.assertIn("image_mime_type", columns_after)
        self.assertEqual(table_count, 7)

    def test_dashboard_shows_joined_catalog_and_replenishment_warning(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Microsoft 365 Business Standard", response.data)
        self.assertIn(b"Risco de Ruptura / Reposi", response.data)
        self.assertIn(b"MicroParts Distribuidora Ltda.", response.data)
        self.assertIn(b"Assinatura anual", response.data)

    def test_create_screens_load_with_catalog_options(self):
        product_page = self.client.get("/products/new")
        movement_page = self.client.get("/movements/new")
        catalogs_page = self.client.get("/catalogs")

        self.assertEqual(product_page.status_code, 200)
        self.assertIn("Armazenamento".encode(), product_page.data)
        self.assertIn("MicroParts Distribuidora Ltda.".encode(), product_page.data)
        self.assertEqual(movement_page.status_code, 200)
        self.assertIn("SSD NVMe 1 TB".encode(), movement_page.data)
        self.assertEqual(catalogs_page.status_code, 200)
        self.assertIn("Categorias".encode(), catalogs_page.data)
        self.assertIn("Fornecedores".encode(), catalogs_page.data)
        self.assertIn('enctype="multipart/form-data"'.encode(), product_page.data)
        self.assertIn('name="image"'.encode(), product_page.data)

    def test_showroom_displays_product_details_and_links_to_checkout(self):
        response = self.client.get("/showroom")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Vitrine de produtos".encode(), response.data)
        self.assertIn("NVMe PCIe 4.0, leitura até 3500 MB/s".encode(), response.data)
        self.assertIn("Assinatura anual".encode(), response.data)
        self.assertIn(b"/sales/new?produto_id=", response.data)
        self.assertIn("Estoque baixo".encode(), response.data)
        self.assertIn("R$ 1.399,00".encode(), response.data)

        selected_product = self.get_product_id("HW-SSD-001")
        checkout = self.client.get(f"/sales/new?produto_id={selected_product}")
        self.assertEqual(checkout.status_code, 200)
        self.assertIn('id="selected-product-preview"'.encode(), checkout.data)
        self.assertIn("data-description=".encode(), checkout.data)
        self.assertIn(
            "/static/images/products/ssd-nvme.svg".encode(), checkout.data
        )

    def test_customer_can_view_the_public_showroom_without_signing_in(self):
        self.client.post("/logout")
        response = self.client.get("/showroom")

        self.assertEqual(response.status_code, 200)
        self.assertIn("TechStore".encode(), response.data)
        self.assertIn("Produtos e soluções".encode(), response.data)
        self.assertIn("Ilustração de SSD NVMe 1 TB".encode(), response.data)
        self.assertIn("Consultar compra".encode(), response.data)

    def test_manager_can_upload_product_photo_for_showroom_and_checkout(self):
        product_id = self.get_product_id("HW-SSD-001")
        image_buffer = BytesIO()
        Image.new("RGB", (4, 3), color=(30, 100, 180)).save(image_buffer, format="PNG")
        response = self.client.post(
            f"/products/{product_id}/image",
            data={"image": (BytesIO(image_buffer.getvalue()), "ssd.png")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Foto do produto atualizada".encode(), response.data)
        with closing(sqlite3.connect(self.database)) as db:
            image = db.execute(
                "SELECT image_data, image_mime_type FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
        self.assertEqual(image[1], "image/png")
        self.assertTrue(image[0].startswith(b"\x89PNG\r\n\x1a\n"))

        image_response = self.client.get(f"/products/{product_id}/image")
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.mimetype, "image/png")
        self.assertEqual(image_response.headers["X-Content-Type-Options"], "nosniff")

        showroom = self.client.get("/showroom")
        self.assertIn(f"/products/{product_id}/image".encode(), showroom.data)
        checkout = self.client.get(f"/sales/new?produto_id={product_id}")
        self.assertIn(f'data-image="/products/{product_id}/image"'.encode(), checkout.data)
        self.client.post("/logout")
        public_image = self.client.get(f"/products/{product_id}/image")
        self.assertEqual(public_image.status_code, 200)
        self.assertEqual(public_image.mimetype, "image/png")

    def test_invalid_product_photo_is_rejected_without_saving(self):
        product_id = self.get_product_id("HW-SSD-001")
        response = self.client.post(
            f"/products/{product_id}/image",
            data={"image": (BytesIO(b"not an image"), "fake.png")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        self.assertIn("Não foi possível ler a imagem".encode(), response.data)
        with closing(sqlite3.connect(self.database)) as db:
            image_data = db.execute(
                "SELECT image_data FROM products WHERE id = ?", (product_id,)
            ).fetchone()[0]
        self.assertIsNone(image_data)

    def test_create_category_supplier_product_and_movements(self):
        response = self.client.post(
            "/catalogs",
            data={"catalog_type": "category", "name": "Acessórios de teste"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Categoria cadastrada".encode(), response.data)

        response = self.client.post(
            "/catalogs",
            data={
                "catalog_type": "supplier",
                "company_name": "Fornecedor de teste Ltda.",
                "cnpj": "98.765.432/0001-10",
                "phone": "(11) 99999-0000",
                "email": "teste@example.com",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Fornecedor cadastrado".encode(), response.data)

        with closing(sqlite3.connect(self.database)) as db:
            category_id = db.execute(
                "SELECT id FROM categories WHERE name = ?",
                ("Acessórios de teste",),
            ).fetchone()[0]
            supplier_id = db.execute(
                "SELECT id FROM suppliers WHERE cnpj = ?",
                ("98.765.432/0001-10",),
            ).fetchone()[0]

        product_image = BytesIO()
        Image.new("RGB", (4, 3), color=(30, 100, 180)).save(product_image, format="JPEG")
        response = self.client.post(
            "/products/new",
            data={
                "sku": "TEST-ACCESSORY-001",
                "name": "Acessório de teste",
                "manufacturer": "Fabricante de teste",
                "item_type": "Periférico",
                "specification": "Produto para validar cadastro",
                "price": "25.50",
                "stock": "2",
                "min_stock": "1",
                "location": "Prateleira de teste",
                "category_id": str(category_id),
                "supplier_id": str(supplier_id),
                "image": (BytesIO(product_image.getvalue()), "acessorio.jpg"),
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ativo cadastrado com sucesso".encode(), response.data)
        product = self.get_product("TEST-ACCESSORY-001")
        with closing(sqlite3.connect(self.database)) as db:
            image_mime_type = db.execute(
                "SELECT image_mime_type FROM products WHERE sku = ?",
                ("TEST-ACCESSORY-001",),
            ).fetchone()[0]
        self.assertEqual(image_mime_type, "image/jpeg")

        for operation, quantity, message in (
            ("Entrada", "3", "Entrada registrada"),
            ("Saída", "1", "Saída registrada"),
        ):
            response = self.client.post(
                "/movements/new",
                data={
                    "product_id": product["id"],
                    "operation": operation,
                    "quantity": quantity,
                    "note": "Teste automatizado",
                },
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(message.encode(), response.data)

        self.assertEqual(self.get_product("TEST-ACCESSORY-001")["stock"], 4)

    def test_rejects_outgoing_movement_above_available_stock(self):
        product = self.get_product("HW-RAM-002")
        response = self.client.post(
            "/movements/new",
            data={
                "product_id": product["id"],
                "operation": "Saída",
                "quantity": "4",
                "note": "Teste de saldo insuficiente",
            },
            follow_redirects=True,
        )
        self.assertIn("Saldo insuficiente".encode(), response.data)
        self.assertEqual(self.get_product("HW-RAM-002")["stock"], 3)

    def test_movement_updates_stock_and_records_audit_entry(self):
        product = self.get_product("HW-RAM-002")
        response = self.client.post(
            "/movements/new",
            data={
                "product_id": product["id"],
                "operation": "Entrada",
                "quantity": "5",
                "note": "Reposição de teste",
            },
            follow_redirects=True,
        )
        self.assertIn("Entrada registrada".encode(), response.data)
        self.assertEqual(self.get_product("HW-RAM-002")["stock"], 8)
        with closing(sqlite3.connect(self.database)) as db:
            movement = db.execute(
                "SELECT operation, quantity, note FROM movements ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(movement, ("Entrada", 5, "Reposição de teste"))

    def test_duplicate_sku_is_rejected(self):
        response = self.client.post(
            "/products/new",
            data={
                "sku": "HW-SSD-001",
                "name": "SSD duplicado",
                "manufacturer": "Marca",
                "item_type": "Hardware",
                "specification": "Teste",
                "price": "10",
                "stock": "0",
                "min_stock": "0",
                "location": "Prateleira",
                "category_id": "1",
                "supplier_id": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("Este SKU já está cadastrado".encode(), response.data)
        with closing(sqlite3.connect(self.database)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM products WHERE sku = 'HW-SSD-001'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_category_with_products_cannot_be_deleted(self):
        response = self.client.post(
            "/catalogs/delete/category/1", follow_redirects=True
        )
        self.assertIn("existem ativos vinculados".encode(), response.data)
        with closing(sqlite3.connect(self.database)) as db:
            category = db.execute(
                "SELECT name FROM categories WHERE id = 1"
            ).fetchone()
        self.assertEqual(category, ("Armazenamento",))

    def test_supplier_with_products_cannot_be_deleted(self):
        response = self.client.post(
            "/catalogs/delete/supplier/1", follow_redirects=True
        )
        self.assertIn("existem ativos vinculados".encode(), response.data)
        with closing(sqlite3.connect(self.database)) as db:
            supplier = db.execute(
                "SELECT company_name FROM suppliers WHERE id = 1"
            ).fetchone()
        self.assertEqual(supplier, ("MicroParts Distribuidora Ltda.",))

    def test_non_positive_product_price_is_rejected(self):
        response = self.client.post(
            "/products/new",
            data={
                "sku": "HW-PRICE-INVALID",
                "name": "Produto inválido",
                "manufacturer": "Marca",
                "item_type": "Hardware",
                "specification": "Teste",
                "price": "0",
                "stock": "0",
                "min_stock": "0",
                "location": "Prateleira",
                "category_id": "1",
                "supplier_id": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("preço deve ser maior que zero".encode(), response.data)
        with closing(sqlite3.connect(self.database)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM products WHERE sku = 'HW-PRICE-INVALID'"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_seeded_accounts_authenticate_and_operator_is_restricted(self):
        self.client.post("/logout")
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self.login_as("operador@techstore.com", "Operador123!")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/sales/new").status_code, 200)
        self.assertEqual(self.client.get("/catalogs").status_code, 200)
        self.assertEqual(self.client.get("/products/new").status_code, 403)
        self.assertEqual(
            self.client.post("/products/1/image").status_code, 403
        )
        self.assertEqual(self.client.get("/movements/new").status_code, 403)
        self.assertEqual(self.client.get("/sales").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/products/{self.get_product_id('HW-RAM-002')}/price",
                data={"price": "0.01"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/catalogs", data={"catalog_type": "category", "name": "Proibida"}
            ).status_code,
            403,
        )

        self.client.post("/logout")
        bad_login = self.login_as("operador@techstore.com", "senha-incorreta")
        self.assertEqual(bad_login.status_code, 401)

    def test_checkout_sells_multiple_items_and_generates_receipt(self):
        self.client.post("/logout")
        self.login_as("operador@techstore.com", "Operador123!")
        product_ids = [
            self.get_product_id("HW-RAM-002"),
            self.get_product_id("SW-M365-004"),
        ]
        response = self.client.post(
            "/sales",
            data={
                "cliente_nome": "Empresa Exemplo Ltda.",
                "cliente_documento": "12.345.678/0001-90",
                "forma_pagamento": "PIX",
                "itens_json": json.dumps(
                    [
                        {"produto_id": product_ids[0], "quantidade": 1},
                        {"produto_id": product_ids[1], "quantidade": 2},
                    ]
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sales/", response.location)
        sale_id = int(response.location.rsplit("/", 1)[1])

        self.assertEqual(self.get_product("HW-RAM-002")["stock"], 2)
        self.assertEqual(self.get_product("SW-M365-004")["stock"], 23)
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            sale = db.execute(
                "SELECT numero_pedido, valor_total, status_venda, chave_autenticidade "
                "FROM vendas WHERE id = ?",
                (sale_id,),
            ).fetchone()
            items = db.execute(
                """
                SELECT quantidade_vendida, preco_unitario_praticado, subtotal_item
                FROM itens_venda WHERE venda_id = ? ORDER BY id
                """,
                (sale_id,),
            ).fetchall()
            movements = db.execute(
                """
                SELECT COUNT(*) FROM movements
                WHERE note LIKE ?
                """,
                (f"%{sale['numero_pedido']}%",),
            ).fetchone()[0]
        self.assertEqual(sale["status_venda"], "CONCLUIDA")
        self.assertAlmostEqual(sale["valor_total"], 2017.90)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["preco_unitario_praticado"], 219.90)
        self.assertEqual(items[1]["subtotal_item"], 1798.00)
        self.assertEqual(movements, 2)

        receipt = self.client.get(response.location)
        self.assertEqual(receipt.status_code, 200)
        self.assertIn("Empresa Exemplo Ltda.".encode(), receipt.data)
        self.assertIn("Licença digital".encode(), receipt.data)
        self.assertIn(sale["numero_pedido"].encode(), receipt.data)
        self.assertIn(sale["chave_autenticidade"].encode(), receipt.data)

    def test_insufficient_later_item_rolls_back_entire_checkout(self):
        self.client.post("/logout")
        self.login_as("operador@techstore.com", "Operador123!")
        first_id = self.get_product_id("HW-RAM-002")
        second_id = self.get_product_id("SW-WIN-005")
        with closing(sqlite3.connect(self.database)) as db:
            sales_before = db.execute("SELECT COUNT(*) FROM vendas").fetchone()[0]
            movements_before = db.execute("SELECT COUNT(*) FROM movements").fetchone()[0]

        response = self.client.post(
            "/sales",
            data={
                "cliente_nome": "Cliente de teste",
                "cliente_documento": "12345678900",
                "forma_pagamento": "CARTAO_CREDITO",
                "itens_json": json.dumps(
                    [
                        {"produto_id": first_id, "quantidade": 1},
                        {"produto_id": second_id, "quantidade": 100},
                    ]
                ),
                "_follow": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("Saldo insuficiente".encode(), response.data)
        self.assertEqual(self.get_product("HW-RAM-002")["stock"], 3)
        self.assertEqual(self.get_product("SW-WIN-005")["stock"], 4)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM vendas").fetchone()[0], sales_before
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM movements").fetchone()[0],
                movements_before,
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM itens_venda").fetchone()[0], 2)

    def test_manager_can_cancel_sale_and_restore_stock_atomically(self):
        self.client.post("/logout")
        self.login_as("operador@techstore.com", "Operador123!")
        product_id = self.get_product_id("HW-RAM-002")
        response = self.client.post(
            "/sales",
            data={
                "cliente_nome": "Cliente para estorno",
                "cliente_documento": "12345678900",
                "forma_pagamento": "BOLETO_FATURADO",
                "itens_json": json.dumps([{"produto_id": product_id, "quantidade": 1}]),
            },
        )
        sale_id = int(response.location.rsplit("/", 1)[1])
        self.assertEqual(self.get_product("HW-RAM-002")["stock"], 2)

        self.client.post("/logout")
        self.login_as("gerente@techstore.com", "Gerente123!")
        response = self.client.post(f"/sales/{sale_id}/cancel")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.get_product("HW-RAM-002")["stock"], 3)
        with closing(sqlite3.connect(self.database)) as db:
            status = db.execute(
                "SELECT status_venda FROM vendas WHERE id = ?", (sale_id,)
            ).fetchone()[0]
            movement = db.execute(
                """
                SELECT operation, quantity, note FROM movements
                WHERE product_id = ? ORDER BY id DESC LIMIT 1
                """,
                (product_id,),
            ).fetchone()
        self.assertEqual(status, "CANCELADA")
        self.assertEqual(movement[0:2], ("Entrada", 1))
        self.assertIn("Estorno", movement[2])

    def test_manager_price_change_does_not_change_frozen_sale_price(self):
        self.client.post("/logout")
        self.login_as("operador@techstore.com", "Operador123!")
        product_id = self.get_product_id("HW-RAM-002")
        response = self.client.post(
            "/sales",
            data={
                "cliente_nome": "Cliente recorrente",
                "cliente_documento": "12345678900",
                "forma_pagamento": "PIX",
                "itens_json": json.dumps([{"produto_id": product_id, "quantidade": 1}]),
            },
        )
        sale_id = int(response.location.rsplit("/", 1)[1])

        self.client.post("/logout")
        self.login_as("gerente@techstore.com", "Gerente123!")
        self.client.post(f"/products/{product_id}/price", data={"price": "999.99"})
        with closing(sqlite3.connect(self.database)) as db:
            product_price = db.execute(
                "SELECT price FROM products WHERE id = ?", (product_id,)
            ).fetchone()[0]
            sale_price = db.execute(
                "SELECT preco_unitario_praticado FROM itens_venda WHERE venda_id = ?",
                (sale_id,),
            ).fetchone()[0]
        self.assertAlmostEqual(product_price, 999.99)
        self.assertAlmostEqual(sale_price, 219.90)


if __name__ == "__main__":
    unittest.main()
