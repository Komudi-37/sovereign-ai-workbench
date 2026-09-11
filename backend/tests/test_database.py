import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import UserModel, SessionModel, MessageModel, DocumentModel, ArtifactModel, AuditLogModel
from app.db import repositories as repo

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_user_creation(db_session):
    user = repo.get_default_user(db_session)
    assert user.username == "admin"
    assert user.role == "admin"

def test_session_and_messages(db_session):
    user = repo.get_default_user(db_session)
    chat_session = repo.create_session(db_session, user.id, title="Test Chat")
    assert chat_session.id is not None
    
    msg1 = repo.create_message(db_session, chat_session.id, "user", "Hello")
    msg2 = repo.create_message(db_session, chat_session.id, "assistant", "Hi there!", model="qwen3:4b")
    
    messages = repo.list_messages(db_session, chat_session.id)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "Hi there!"

def test_document_and_chunks(db_session):
    doc = repo.create_document(
        db_session,
        filename="test.pdf",
        path="/tmp/test.pdf",
        mime_type="application/pdf",
        size=1024,
        checksum="abc123hash",
        status="uploaded"
    )
    assert doc.id is not None
    
    repo.create_chunks_bulk(db_session, [
        {"document_id": doc.id, "chunk_index": 0, "text": "Chunk 1", "page_number": 1},
        {"document_id": doc.id, "chunk_index": 1, "text": "Chunk 2", "page_number": 1},
    ])
    
    chunks = repo.get_chunks_for_document(db_session, doc.id)
    assert len(chunks) == 2
    assert chunks[0].text == "Chunk 1"

def test_audit_logs(db_session):
    log = repo.create_audit_log(
        db_session,
        action="TEST_ACTION",
        agent_name="test_agent",
        resource="test_resource",
        metadata={"detail": "success"}
    )
    assert log.id is not None
    logs = repo.list_audit_logs(db_session)
    assert len(logs) == 1
    assert logs[0].action == "TEST_ACTION"
