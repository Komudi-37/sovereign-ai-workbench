import pytest
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import UserModel, SessionModel, MessageModel
from app.db import repositories as repo
from app.services.title_generator import generate_conversation_title

TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture
def db():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

# Test A: Create conversation
def test_a_create_conversation(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Test Conversation")
    assert conv.id is not None
    assert conv.title == "Test Conversation"
    assert conv.created_at is not None

# Test B: List conversations
def test_b_list_conversations(db):
    user = repo.get_default_user(db)
    conv1 = repo.create_session(db, user_id=user.id, title="Chat 1")
    conv2 = repo.create_session(db, user_id=user.id, title="Chat 2")
    convs = repo.list_sessions(db)
    assert len(convs) >= 2
    titles = [c.title for c in convs]
    assert "Chat 1" in titles
    assert "Chat 2" in titles

# Test C: Save user message in conversation
def test_c_save_user_message(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Message Test")
    msg = repo.create_message(db, conv.id, "user", "What are the limits for ISO 10816?", metadata={"document_ids": ["doc-1"]})
    assert msg.id is not None
    assert msg.role == "user"
    assert msg.content == "What are the limits for ISO 10816?"
    assert msg.metadata_json is not None
    assert "doc-1" in msg.metadata_json

# Test D: Save assistant message with metadata
def test_d_save_assistant_message_with_metadata(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Assistant Test")
    meta = {
        "citations": [{"filename": "SOP-MAINT-001.txt", "page": 4}],
        "timeline": [{"label": "RAG Agent", "status": "completed"}],
        "artifacts": [{"id": "art-1", "filename": "report.docx"}],
    }
    msg = repo.create_message(db, conv.id, "assistant", "Limits are < 2.8 mm/s.", model="sovereign-rag-agent", metadata=meta)
    assert msg.role == "assistant"
    parsed = json.loads(msg.metadata_json)
    assert parsed["citations"][0]["filename"] == "SOP-MAINT-001.txt"
    assert parsed["timeline"][0]["status"] == "completed"

# Test E: Retrieve complete conversation
def test_e_retrieve_complete_conversation(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Full Conv")
    repo.create_message(db, conv.id, "user", "User query")
    repo.create_message(db, conv.id, "assistant", "Assistant response", metadata={"timeline": [{"label": "RAG", "status": "completed"}]})
    
    full = repo.get_conversation_with_messages(db, conv.id)
    assert full is not None
    assert full["id"] == conv.id
    assert full["title"] == "Full Conv"
    assert len(full["messages"]) == 2
    assert full["messages"][1]["timeline"][0]["label"] == "RAG"

# Test F: Continue existing conversation (multiple turns)
def test_f_continue_conversation(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Multi-turn")
    for i in range(3):
        repo.create_message(db, conv.id, "user", f"Turn {i} user")
        repo.create_message(db, conv.id, "assistant", f"Turn {i} assistant")
    msgs = repo.list_messages(db, conv.id)
    assert len(msgs) == 6

# Test G: Rename conversation
def test_g_rename_conversation(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Old Title")
    updated = repo.update_session_title(db, conv.id, "New Renamed Title")
    assert updated.title == "New Renamed Title"
    refetched = repo.get_session(db, conv.id)
    assert refetched.title == "New Renamed Title"

# Test H: Delete conversation and cascade messages
def test_h_delete_conversation(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="To Delete")
    repo.create_message(db, conv.id, "user", "Delete me")
    success = repo.delete_session(db, conv.id)
    assert success is True
    assert repo.get_session(db, conv.id) is None
    # Messages should be deleted
    assert len(repo.list_messages(db, conv.id)) == 0

# Test I: Preserve timeline, citations, artifacts across retrieval
def test_i_preserve_rich_metadata(db):
    user = repo.get_default_user(db)
    conv = repo.create_session(db, user_id=user.id, title="Rich Meta")
    repo.create_message(db, conv.id, "assistant", "Rich response", metadata={
        "citations": [{"filename": "doc.pdf", "page": 1, "text": "snippet", "citation": "[Source: doc.pdf]"}],
        "artifacts": [{"id": "1", "filename": "sheet.xlsx", "download_url": "/api/artifacts/1/download"}],
        "timeline": [{"label": "DATA ANALYSIS Agent", "status": "completed"}],
        "execution_plan": {"intent": "DATA_ANALYSIS", "confidence": 0.95}
    })
    res = repo.get_conversation_with_messages(db, conv.id)
    asst_msg = res["messages"][0]
    assert asst_msg["citations"][0]["filename"] == "doc.pdf"
    assert asst_msg["artifacts"][0]["filename"] == "sheet.xlsx"
    assert asst_msg["timeline"][0]["label"] == "DATA ANALYSIS Agent"
    assert asst_msg["executionPlan"]["intent"] == "DATA_ANALYSIS"

# Test J: Persist across simulated backend restart (file-backed SQLite)
def test_j_persist_across_restart(tmp_path):
    db_file = tmp_path / "restart_test.db"
    engine1 = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine1)
    Session1 = sessionmaker(bind=engine1)
    s1 = Session1()
    user = repo.get_default_user(s1)
    conv = repo.create_session(s1, user_id=user.id, title="Persistent Chat")
    conv_id = conv.id
    repo.create_message(s1, conv_id, "user", "Saved before restart")
    repo.create_message(s1, conv_id, "assistant", "Answer before restart")
    s1.close()
    engine1.dispose()

    # Simulate restart with new engine & session to same file
    engine2 = create_engine(f"sqlite:///{db_file}")
    Session2 = sessionmaker(bind=engine2)
    s2 = Session2()
    restarted_conv = repo.get_conversation_with_messages(s2, conv_id)
    assert restarted_conv is not None
    assert restarted_conv["title"] == "Persistent Chat"
    assert len(restarted_conv["messages"]) == 2
    assert restarted_conv["messages"][0]["content"] == "Saved before restart"
    s2.close()
    engine2.dispose()

# Test K: Deterministic Title Generator
def test_k_title_generator():
    t1 = generate_conversation_title("What are the vibration velocity thresholds specified in the available SOP for ISO 10816?")
    assert "Vibration" in t1 or "Velocity" in t1 or "ISO 10816" in t1
    t2 = generate_conversation_title("Analyze the uploaded equipment telemetry dataset and identify abnormal readings.")
    assert "Telemetry" in t2 or "Equipment" in t2 or "Analysis" in t2
    t3 = generate_conversation_title("Review this inspection report and summarize the major maintenance risks.")
    assert "Inspection" in t3 or "Maintenance" in t3 or "Report" in t3
    t4 = generate_conversation_title("Hello there")
    assert t4.lower() == "hello there"
