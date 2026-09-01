"""Tests for Datara domain models."""

from datetime import datetime

from core.models import (
    Archive,
    AuthSession,
    ChatSession,
    CodeArtifact,
    DataProfile,
    Message,
    UploadedFile,
    User,
)


class TestUser:
    def test_create(self):
        user = User(id=1, email="alice@example.com", password_hash="abc", created_at=datetime(2026, 1, 1))
        assert user.id == 1
        assert user.email == "alice@example.com"
        assert user.password_hash == "abc"

    def test_frozen(self):
        user = User(id=1, email="a@b.com", password_hash="x", created_at=datetime(2026, 1, 1))
        try:
            user.email = "other@b.com"
            assert False, "should be frozen"
        except AttributeError:
            pass


class TestAuthSession:
    def test_create(self):
        session = AuthSession(
            id=1,
            user_id=1,
            token_hash="abc123",
            created_at=datetime(2026, 1, 1),
            expires_at=datetime(2026, 1, 1, 8),
            last_seen_at=datetime(2026, 1, 1),
        )
        assert session.id == 1
        assert session.user_id == 1
        assert session.token_hash == "abc123"
        assert session.expires_at > session.created_at


class TestChatSession:
    def test_create_with_default_title(self):
        session = ChatSession(
            id="ses_abc",
            user_id=1,
            title="New chat",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert session.id == "ses_abc"
        assert session.title == "New chat"

    def test_create_custom_title(self):
        session = ChatSession(
            id="ses_def",
            user_id=1,
            title="My Analysis",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert session.title == "My Analysis"


class TestMessage:
    def test_user_message(self):
        msg = Message(
            id=1,
            user_id=1,
            chat_session="ses_abc",
            role="user",
            content_text="What is the average?",
        )
        assert msg.role == "user"
        assert msg.code is None

    def test_assistant_message(self):
        msg = Message(
            id=2,
            user_id=1,
            chat_session="ses_abc",
            role="assistant",
            content_text="Here is the analysis",
            code="print('hello')",
            model="gpt-4o",
            provider="openai",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.002,
        )
        assert msg.role == "assistant"
        assert msg.code == "print('hello')"
        assert msg.tokens_in == 100


class TestUploadedFile:
    def test_create(self):
        f = UploadedFile(
            id=1,
            user_id=1,
            chat_session="ses_abc",
            filename="data.csv",
            storage_path="uploads/1/ses_abc/data.csv",
            size_bytes=1024,
            format="csv",
        )
        assert f.filename == "data.csv"
        assert f.format == "csv"


class TestDataProfile:
    def test_create(self):
        profile = DataProfile(
            file_id=1,
            schema_json='{"columns":["a","b"]}',
            stats_json='{"a":{"mean":1.0}}',
            sample_json='[{"a":1,"b":2}]',
        )
        assert profile.file_id == 1


class TestCodeArtifact:
    def test_figure_artifact(self):
        art = CodeArtifact(name="fig1", kind="figure", payload_json='{"data":[]}')
        assert art.kind == "figure"
        assert art.name == "fig1"

    def test_table_artifact(self):
        art = CodeArtifact(name="table1", kind="table", payload_json='{"rows":[]}')
        assert art.kind == "table"


class TestArchive:
    def test_create(self):
        arch = Archive(
            id=1,
            user_id=1,
            name="Backup Jan",
            chat_session="ses_abc",
            payload_json='{"messages":[]}',
        )
        assert arch.name == "Backup Jan"