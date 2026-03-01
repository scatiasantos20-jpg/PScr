import unittest

from scrapers.common.export_schema import ensure_export_schema, validate_export_schema


class TestExportSchema(unittest.TestCase):
    def test_bol_valid_minimum_aliases(self):
        rows = [
            {
                "Nome da Peça": "Peça X",
                "Link da Peça": "https://exemplo/peca-x",
                "Horários": "2026-04-01T21:00",
                "Preço Formatado": "15€",
            }
        ]
        result = validate_export_schema("bol", rows)
        self.assertTrue(result.ok)
        self.assertEqual(result.missing_logical_fields, ())

    def test_ticketline_missing_price(self):
        rows = [
            {
                "Nome da Peça": "Peça Y",
                "Link da Peça": "https://exemplo/peca-y",
                "Horários": "2026-04-02T21:00",
            }
        ]
        result = validate_export_schema("ticketline", rows)
        self.assertFalse(result.ok)
        self.assertIn("price", result.missing_logical_fields)

    def test_unknown_platform_uses_default_requirements(self):
        rows = [{"Title": "Show", "Event URL": "https://example/show"}]
        ensure_export_schema("nova_plataforma", rows)  # não deve lançar

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            ensure_export_schema("bol", [])


if __name__ == "__main__":
    unittest.main()
