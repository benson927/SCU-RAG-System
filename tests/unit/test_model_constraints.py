import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Document, DocumentVersion, IndexJob


class TestModelConstraints(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def test_rejects_invalid_document_version_status(self):
        with self.Session() as session:
            document = Document(title="Constraint Law", source_alias="constraint.pdf")
            session.add(document)
            session.flush()
            session.add(
                DocumentVersion(
                    document_id=document.id,
                    title=document.title,
                    version_number="1.0",
                    original_filename="constraint.pdf",
                    object_key="documents/constraint.pdf",
                    checksum="a" * 64,
                    size_bytes=10,
                    status="invalid",
                )
            )
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_rejects_invalid_job_status(self):
        with self.Session() as session:
            session.add(IndexJob(trigger="test", status="invalid"))
            with self.assertRaises(IntegrityError):
                session.commit()


if __name__ == "__main__":
    unittest.main()
