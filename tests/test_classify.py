import unittest
from pathlib import Path

from collector import config
from collector.classify import Classifier

ROOT = Path(__file__).resolve().parents[1]


class ClassifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = config.load(ROOT)
        cls.clf = Classifier(cls.cfg.classification)

    def verdict(self, title, department="", section="", summary="", subsection=""):
        return self.clf.classify({"title": title, "department": department,
                                  "section": section, "summary": summary,
                                  "subsection": subsection})

    def test_impact_statement_is_relevant(self):
        v = self.verdict("Resolución por la que se formula declaración de impacto ambiental "
                         "del proyecto de planta solar")
        self.assertTrue(v.relevant)
        self.assertIn("evaluacion-ambiental", v.topics)

    def test_routine_administrative_notice_is_not_relevant(self):
        v = self.verdict("Anuncio de licitación de contrato de limpieza de edificios",
                         department="MINISTERIO DE HACIENDA")
        self.assertFalse(v.relevant)

    def test_staffing_notice_from_environment_department_is_excluded(self):
        v = self.verdict("Resolución por la que se publica el tribunal calificador del "
                         "proceso selectivo", department="CONSEJERÍA DE MEDIO AMBIENTE")
        self.assertFalse(v.relevant)

    def test_accents_and_case_do_not_matter(self):
        with_accents = self.verdict("Declaración de Impacto Ambiental del proyecto")
        without = self.verdict("DECLARACION DE IMPACTO AMBIENTAL DEL PROYECTO")
        self.assertEqual(with_accents.score, without.score)
        self.assertTrue(without.relevant)

    def test_word_boundaries(self):
        # "agua" must not fire inside "aguardiente"
        v = self.verdict("Orden sobre la denominación de origen del aguardiente")
        self.assertFalse(v.relevant)

    def test_environmental_department_adds_score_but_is_not_enough(self):
        v = self.verdict("Corrección de errores de la resolución de 3 de junio",
                         department="MINISTERIO PARA LA TRANSICIÓN ECOLÓGICA")
        self.assertGreater(v.score, 0)

    def test_document_types(self):
        v = self.verdict("Orden por la que se establecen las bases reguladoras de las "
                         "subvenciones para la restauración de humedales")
        self.assertTrue(v.relevant)
        self.assertIn("ayudas", v.doc_types)

    def test_threshold_is_configurable(self):
        rules = dict(self.cfg.classification)
        rules["scoring"] = dict(rules["scoring"], min_score=99)
        strict = Classifier(rules)
        v = strict.classify({"title": "declaración de impacto ambiental"})
        self.assertFalse(v.relevant)


if __name__ == "__main__":
    unittest.main()
