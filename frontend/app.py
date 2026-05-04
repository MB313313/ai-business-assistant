"""Streamlit chat UI for the AI Business Assistant (FastAPI RAG backend)."""

from __future__ import annotations

import base64
import html
import mimetypes
import os
from io import BytesIO
from pathlib import Path

import requests
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

_DEFAULT_API = "http://127.0.0.1:8000"
_TIMEOUT = 120

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_PATH = _PROJECT_ROOT / "samples" / "apex_digital_hr_faq.txt"


def _api_base() -> str:
    raw = st.session_state.get("api_base_url") or os.environ.get("API_BASE_URL", _DEFAULT_API)
    return str(raw).strip().rstrip("/")


def _friendly_request_error(exc: BaseException) -> str:
    if isinstance(exc, requests.Timeout):
        return (
            "This is taking longer than expected. Please wait a moment and try again, "
            "or try a smaller document."
        )
    if isinstance(exc, requests.ConnectionError):
        return (
            "We could not reach the assistant. Check your internet connection, "
            "and confirm the **service link** in the sidebar is correct."
        )
    if isinstance(exc, requests.RequestException):
        return "A connection problem occurred. Please try again in a moment."
    return "Something went wrong. Please try again."


def _error_detail(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        return (resp.text or "").strip() or resp.reason
    detail = data.get("detail") if isinstance(data, dict) else None
    if detail is None:
        return (resp.text or "").strip() or resp.reason
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                parts.append(str(item["msg"]))
            else:
                parts.append(str(item))
        return "; ".join(parts)
    return str(detail)


def _public_error_message(resp: requests.Response) -> str:
    """Short, non-technical copy for people using the assistant (no HTTP codes or stack hints)."""
    code = resp.status_code
    detail_lower = _error_detail(resp).lower()

    if code == 503:
        return "The assistant is temporarily unavailable. Please try again later or ask your IT contact for help."

    if code == 502:
        if any(
            w in detail_lower
            for w in ("quota", "billing", "insufficient", "rate limit", "429", "payment")
        ):
            return (
                "The AI service is temporarily at its usage limit. "
                "Please try again later, or ask your administrator to check the service account."
            )
        return "The assistant had a problem completing this step. Please try again in a moment."

    if code == 404:
        return "This action could not be found. The service link may need updating—ask your administrator."

    if code == 400:
        return "We could not use that file or question as-is. Try another file or rephrase your question."

    if code == 422:
        return "Please check your message or attachments and try again."

    if code == 413:
        return "That file is too large. Try a smaller document."

    if code in (401, 403):
        return "You do not have access to this action. Contact your administrator."

    if 500 <= code < 600:
        return "The assistant hit a temporary issue. Please try again shortly."

    return "Something went wrong. Please try again, or contact your administrator if this keeps happening."


def _raise_for_status(resp: requests.Response) -> None:
    if resp.ok:
        return
    raise RuntimeError(_public_error_message(resp))


def _get_json(url: str) -> dict:
    try:
        r = requests.get(url, timeout=15)
    except requests.RequestException as e:
        raise RuntimeError(_friendly_request_error(e)) from e
    _raise_for_status(r)
    try:
        return r.json()
    except Exception as e:
        raise RuntimeError("We could not read the service response. Please try again.") from e


def _post_json(url: str, *, json_body: dict | None = None) -> dict:
    try:
        r = requests.post(url, json=json_body or {}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(_friendly_request_error(e)) from e
    _raise_for_status(r)
    try:
        return r.json()
    except Exception as e:
        raise RuntimeError("We could not read the service response. Please try again.") from e


def _video_first_frame_png(video_bytes: bytes) -> bytes | None:
    """Return PNG bytes of the first video frame, or ``None`` if conversion fails."""
    import tempfile

    try:
        import imageio.v3 as iio
        import numpy as np
        from PIL import Image
    except ImportError:
        return None

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        path = tmp.name
    try:
        frame = iio.imread(path, index=0)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    try:
        os.unlink(path)
    except OSError:
        pass

    try:
        img = Image.fromarray(np.asarray(frame)).convert("RGB")
        bio = BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()
    except Exception:
        return None


def _encode_chat_attachments(files: list) -> list[dict[str, str]]:
    """Build ``images`` payload for ``POST /chat`` from Streamlit uploaded files."""
    out: list[dict[str, str]] = []
    for f in files:
        name = (f.name or "").lower()
        raw = f.getvalue()
        if not raw:
            continue
        if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) or (f.type or "").startswith("image/"):
            mt = mimetypes.guess_type(f.name)[0]
            if not mt:
                if name.endswith(".png"):
                    mt = "image/png"
                elif name.endswith(".webp"):
                    mt = "image/webp"
                elif name.endswith(".gif"):
                    mt = "image/gif"
                else:
                    mt = "image/jpeg"
            b64 = base64.standard_b64encode(raw).decode("ascii")
            out.append({"media_type": mt, "base64_data": b64})
            continue
        if name.endswith((".mp4", ".webm", ".mov")) or (f.type or "").startswith("video/"):
            png = _video_first_frame_png(raw)
            if png is None:
                continue
            b64 = base64.standard_b64encode(png).decode("ascii")
            out.append({"media_type": "image/png", "base64_data": b64})
    return out


def _post_chat(base: str, message: str, images: list[dict[str, str]] | None = None) -> str:
    url = f"{base}/chat"
    payload: dict = {"message": message, "images": images or []}
    data = _post_json(url, json_body=payload)
    return str(data.get("reply", "")).strip()


def _upload_document(base: str, filename: str, content: bytes, mime: str | None) -> tuple[str, int]:
    url = f"{base}/upload-document"
    files = {"file": (filename, content, mime or "application/octet-stream")}
    try:
        r = requests.post(url, files=files, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(_friendly_request_error(e)) from e
    _raise_for_status(r)
    try:
        up = r.json()
    except Exception as e:
        raise RuntimeError("The upload finished, but we could not confirm the result. Please try again.") from e
    doc_id = str(up.get("document_id", ""))
    if not doc_id:
        raise RuntimeError("We could not register your document. Please try uploading again.")
    chunks = int(up.get("chunk_count", 0))
    return doc_id, chunks


def _index_document(base: str, document_id: str) -> None:
    url = f"{base}/vector/index"
    _post_json(url, json_body={"document_id": document_id})


def _sample_document_bytes() -> tuple[bytes, str]:
    if not _SAMPLE_PATH.is_file():
        raise FileNotFoundError("missing_sample")
    text = _SAMPLE_PATH.read_bytes()
    return text, _SAMPLE_PATH.name


def _thumb_data_url(uploaded_file) -> str | None:
    name = (uploaded_file.name or "").lower()
    if not (
        name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        or (uploaded_file.type or "").startswith("image/")
    ):
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        raw = uploaded_file.getvalue()
        im = Image.open(BytesIO(raw)).convert("RGB")
        im.thumbnail((88, 88))
        bio = BytesIO()
        im.save(bio, format="JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.standard_b64encode(bio.getvalue()).decode("ascii")
    except Exception:
        return None


def _media_chips_html(files: list) -> str:
    if not files:
        return ""
    chips: list[str] = []
    for uf in files:
        label = html.escape((uf.name or "Attachment")[:56])
        thumb = _thumb_data_url(uf)
        if thumb:
            chips.append(
                f'<div class="cg-chip cg-chip-media">'
                f'<img class="cg-chip-img" src="{thumb}" alt="" />'
                f'<div class="cg-chip-text"><span class="cg-chip-name">{label}</span>'
                f'<span class="cg-chip-sub">Image</span></div></div>'
            )
        else:
            chips.append(
                f'<div class="cg-chip cg-chip-file">'
                f'<div class="cg-chip-icon">▣</div>'
                f'<div class="cg-chip-text"><span class="cg-chip-name">{label}</span>'
                f'<span class="cg-chip-sub">File</span></div></div>'
            )
    return '<div class="cg-attach-row">' + "".join(chips) + "</div>"


def _inject_chatgpt_styles() -> None:
    st.markdown(
        """
<style>
  /* App shell */
  .stApp { background-color: #212121 !important; color: #ececec !important; }
  .block-container { padding-top: 1.25rem !important; max-width: 880px !important; }
  header[data-testid="stHeader"] { background: transparent !important; }
  div[data-testid="stToolbar"] { display: none !important; }

  /* Typography */
  h1 { font-size: 1.35rem !important; font-weight: 600 !important; letter-spacing: -0.02em !important; }
  .cg-subtitle { color: #b4b4b4 !important; font-size: 0.9rem !important; margin-top: -0.5rem !important; }

  /* Sidebar */
  section[data-testid="stSidebar"] {
    background-color: #171717 !important;
    border-right: 1px solid #303030 !important;
  }
  section[data-testid="stSidebar"] .block-container { padding-top: 1rem !important; }

  /* Chat bubbles */
  [data-testid="stChatMessage"] { background: transparent !important; }
  [data-testid="stChatMessage"] > div {
    border-radius: 18px !important;
    padding: 0.65rem 0.85rem !important;
  }

  .cg-attach-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
  }
  .cg-chip {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #3a3a3a;
    border: 1px solid #555;
    border-radius: 12px;
    padding: 6px 10px 6px 6px;
    min-height: 52px;
    max-width: 100%;
  }
  .cg-chip-img {
    width: 44px;
    height: 44px;
    border-radius: 8px;
    object-fit: cover;
    flex-shrink: 0;
  }
  .cg-chip-icon {
    width: 44px;
    height: 44px;
    border-radius: 8px;
    background: #2f2f2f;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.1rem;
    color: #c8c8c8;
    flex-shrink: 0;
  }
  .cg-chip-text { display: flex; flex-direction: column; min-width: 0; }
  .cg-chip-name { font-size: 0.82rem; color: #ececec; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }
  .cg-chip-sub { font-size: 0.72rem; color: #9a9a9a; }

  /* File uploaders — ChatGPT-like drop zone */
  [data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] {
    background: #2a2a2a !important;
    border: 1px dashed #5a5a5a !important;
    border-radius: 14px !important;
  }
  [data-testid="stFileUploader"] small { color: #b0b0b0 !important; }

  .cg-plus { font-size: 1.45rem; color: #c4c4c4; padding: 10px 0 0 4px; user-select: none; line-height: 1; }

  /* Chat input — pill like ChatGPT */
  [data-testid="stChatInput"] {
    background-color: #2f2f2f !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 26px !important;
    padding: 4px 6px !important;
  }
  [data-testid="stChatInput"] textarea {
    color: #ececec !important;
    background: transparent !important;
    border: none !important;
    min-height: 44px !important;
    font-size: 0.98rem !important;
  }
  [data-testid="stChatInput"] textarea::placeholder {
    color: #8e8e8e !important;
  }
  [data-testid="stChatInput"] button {
    border-radius: 999px !important;
    background: #ececec !important;
    color: #212121 !important;
  }

  /* Buttons */
  .stButton > button {
    border-radius: 10px !important;
  }
</style>
""",
        unsafe_allow_html=True,
    )


st.set_page_config(
    page_title="AI Business Assistant",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

_inject_chatgpt_styles()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = os.environ.get("API_BASE_URL", _DEFAULT_API)
if "media_widget_id" not in st.session_state:
    st.session_state.media_widget_id = 0

st.title("AI Business Assistant")
st.markdown('<p class="cg-subtitle">Company documents + optional images. Answers stay grounded in what you indexed.</p>', unsafe_allow_html=True)

with st.expander("How to use", expanded=False):
    st.markdown(
        "1. **Test connection** in the sidebar.  \n"
        "2. **Upload** a PDF, TXT, or image and **add to knowledge base**.  \n"
        "3. **Ask anything** below — you can attach photos or a short video (first frame).  \n"
        "Tip: use the sample HR / FAQ from the sidebar if you need a quick demo file."
    )

with st.sidebar:
    st.header("Workspace")
    st.markdown("**Connection**")
    st.caption("Your organization runs the assistant service. It must be available before chat or uploads work.")
    st.session_state.api_base_url = st.text_input(
        "Service link",
        value=st.session_state.api_base_url,
        help="The web address of your assistant service (your IT team usually provides this).",
    )
    base = _api_base()

    if st.button("Test connection", use_container_width=True, help="Checks whether the assistant service is reachable."):
        with st.spinner("Checking…"):
            try:
                health = _get_json(f"{base}/health")
                if health.get("status") == "ok":
                    st.success("You are connected. You can upload documents and start chatting.")
                else:
                    st.warning("The service responded, but something looks unusual. Try again or contact support.")
            except RuntimeError as e:
                st.error(str(e))

    st.divider()
    st.markdown("**Your documents**")
    st.caption(
        "Upload a **PDF**, **text file**, or a **chart/photo** (PNG, JPG, etc.). "
        "Images are turned into a short text description for search; PDFs also get embedded figures described."
    )
    uploaded = st.file_uploader(
        "Choose a file",
        type=["pdf", "txt", "png", "jpg", "jpeg", "webp", "gif"],
        label_visibility="visible",
    )

    if st.button(
        "Upload & add to knowledge base",
        use_container_width=True,
        disabled=uploaded is None,
        help="Reads your file and adds it to what the assistant can search.",
    ):
        if uploaded is None:
            st.error("Please choose a file first.")
        else:
            name = uploaded.name or "document.txt"
            data = uploaded.getvalue()
            mime = uploaded.type
            try:
                with st.status("Working on your document…", expanded=True) as status:
                    status.write("Reading your file…")
                    doc_id, _chunk_count = _upload_document(base, name, data, mime)
                    status.write("Making your document searchable…")
                    _index_document(base, doc_id)
                    status.update(
                        label="Your document is ready",
                        state="complete",
                    )
                st.success("Your document is ready. You can ask questions about it in the chat below.")
                st.toast("Knowledge base updated.", icon="✅")
            except RuntimeError as e:
                st.error(str(e))
                st.toast("Something went wrong—see the message above.", icon="⚠️")

    st.divider()
    st.markdown("**Sample for presentations**")
    st.caption("Download an example HR policy and FAQ you can upload to try the assistant.")
    try:
        sample_bytes, sample_name = _sample_document_bytes()
        st.download_button(
            label="Download sample HR & FAQ (TXT)",
            data=sample_bytes,
            file_name=sample_name,
            mime="text/plain",
            use_container_width=True,
        )
    except FileNotFoundError:
        st.warning("The sample file is missing from this installation. Ask your administrator.")

    st.divider()
    if st.button("Clear conversation", use_container_width=True, help="Clears this chat in your browser only."):
        st.session_state.messages = []
        st.rerun()

st.subheader("Chat")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

st.caption("Add files for your next message, then use **Ask anything** or **Send files**.")

row_u = st.columns([0.06, 0.94])
with row_u[0]:
    st.markdown('<div class="cg-plus" title="Add files">＋</div>', unsafe_allow_html=True)
with row_u[1]:
    media_widget_key = f"chat_media_{st.session_state.media_widget_id}"
    media_files = st.file_uploader(
        "Photos or short video",
        type=["png", "jpg", "jpeg", "webp", "gif", "mp4", "webm", "mov"],
        accept_multiple_files=True,
        key=media_widget_key,
        label_visibility="visible",
        help="Videos use the first frame as a still image.",
    )

media_list = list(media_files) if media_files else []
images_payload = _encode_chat_attachments(media_list)
if media_list:
    st.markdown(_media_chips_html(media_list), unsafe_allow_html=True)

send_attachments_only = st.button(
    "Send files",
    disabled=not media_list,
    help="Send attachments without typing a message.",
)

prompt = st.chat_input("Ask anything")
chat_submitted = prompt is not None
user_text = (prompt or "").strip() if chat_submitted else ""

send_go = bool(send_attachments_only and images_payload)
chat_go = bool(chat_submitted and (user_text or images_payload))
go = send_go or chat_go

if send_attachments_only and media_list and not images_payload:
    st.warning("We could not prepare those attachments. Try JPG, PNG, WebP, GIF, or a small MP4.")

if go:
    if media_list and not images_payload:
        st.warning("We could not prepare those attachments. Try JPG, PNG, WebP, GIF, or a small MP4.")
    else:
        display = user_text if user_text else "*Question with attachment*"
        if images_payload:
            display += f"\n\n*{len(images_payload)} image(s) sent with your message.*"

        st.session_state.messages.append({"role": "user", "content": display})
        with st.chat_message("user"):
            st.markdown(display)

        with st.chat_message("assistant"):
            try:
                with st.status("Preparing your answer…", expanded=False) as status:
                    status.write("Finding the most relevant parts of your documents…")
                    reply = _post_chat(base, user_text, images=images_payload or None)
                    status.update(label="Answer ready", state="complete")
            except RuntimeError:
                reply = (
                    "I could not complete that request right now. "
                    "Please try again in a moment. If the problem continues, contact your administrator."
                )
                st.error("We could not get an answer. Please try again.")
            st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.session_state.media_widget_id = int(st.session_state.media_widget_id) + 1
        st.rerun()
