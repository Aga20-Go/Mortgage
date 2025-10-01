import os
from typing import List

import streamlit as st
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# -----------------------------------------------------------------------------
# Page config
# -----------------------------------------------------------------------------
st.set_page_config(page_title="KPR.AI", page_icon="🏠")

# -----------------------------------------------------------------------------
# Bootstrap & constants
# -----------------------------------------------------------------------------
load_dotenv()  # loads .env in current working dir

APP_TITLE = "🏠 KPR Advisor"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.5

# Default policy knobs (you can tweak)
DEFAULT_MAX_DSR = 0.60  # 60% of net income
DEFAULT_MAX_LTV = 0.95  # 95% LTV
CURRENCY = "IDR"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def resolve_google_api_key() -> str:
    """
    Priority:
    1) st.secrets["GOOGLE_API_KEY"]
    2) env var GOOGLE_API_KEY (including values loaded from .env)
    """
    try:
        if "GOOGLE_API_KEY" in st.secrets and st.secrets["GOOGLE_API_KEY"]:
            return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        pass
    env_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if env_key:
        return env_key
    return ""


def init_llm(key: str, model_name: str, temp: float) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=key, temperature=temp)


# --- display formatters (no trailing decimals) --------------------------------
def rupiah(x: float) -> str:
    """Rp with thousands separators, no decimals (Rp5,000)."""
    try:
        return f"Rp{int(round(x)):,.0f}"
    except Exception:
        return f"Rp{x}"

def fmt_int(x: float) -> str:
    """Plain number with thousands separators, no decimals (5,000)."""
    try:
        return f"{int(round(x)):,.0f}"
    except Exception:
        return str(x)

def fmt_decimal_trim(x: float) -> str:
    """
    Decimal number without unnecessary trailing zeros.
    e.g. 10.0 -> '10', 10.50 -> '10.5'
    """
    try:
        s = f"{float(x)}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    except Exception:
        return str(x)

def format_decimal_with_commas(x: float) -> str:
    """
    Format decimal with thousand separators on integer part only:
    12345.6 -> '12,345.6' ; 10000.0 -> '10,000'
    """
    try:
        s = fmt_decimal_trim(x)
        if "." in s:
            int_part, frac = s.split(".", 1)
            return f"{int(int_part):,}.{frac}"
        else:
            return f"{int(s):,}"
    except Exception:
        return str(x)

# --- parsers (accept '5,000,000' and '5.000.000') -----------------------------
def parse_money(text: str) -> float:
    """
    Parse currency-like inputs.
    Accepts '5,000,000', '5.000.000', '5000000', '  5 000 000  '.
    Returns float of the integer value.
    """
    if text is None:
        return 0.0
    s = str(text).strip()
    if s == "":
        return 0.0
    # Remove common thousand separators and spaces
    s = s.replace(" ", "")
    # If contains both ',' and '.', assume commas are thousands and '.' decimal
    # For money we treat value as integer; strip both ',' and '.'
    s = s.replace(",", "").replace(".", "")
    if s == "" or s == "-":
        return 0.0
    try:
        return float(int(s))
    except Exception:
        return 0.0

def parse_decimal(text: str) -> float:
    """
    Parse percentages/decimals.
    Accepts '10', '10.5', '10,5' (both dot or comma as decimal).
    Also accepts thousand separators on int part: '12,345.6'
    """
    if text is None:
        return 0.0
    s = str(text).strip()
    if s == "":
        return 0.0
    s = s.replace(" ", "")
    # normalize decimal separator to '.'
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        # remove thousands commas
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return 0.0

# --- text-input widgets with formatting ---------------------------------------
def money_text_input(label: str, key: str, placeholder: str = "") -> float:
    """
    A text_input that shows '5,000' and parses various user formats to float.
    Uses an internal text key to avoid feedback loops.
    """
    # read current numeric value from session (default 0)
    current_val = float(st.session_state.get(key, 0.0))
    # show formatted text
    text_key = f"{key}__text"
    default_str = fmt_int(current_val)
    user_str = st.text_input(label, value=default_str, key=text_key, placeholder=placeholder)
    parsed = parse_money(user_str)
    st.session_state[key] = parsed
    return parsed

def percent_text_input(label: str, key: str, placeholder: str = "", min_val: float = 0.0, max_val: float = 100.0) -> float:
    """
    A text_input for percentage that trims trailing zeros and validates range.
    Displays like '10' or '10.5' (no trailing .0).
    """
    current_val = float(st.session_state.get(key, 0.0))
    text_key = f"{key}__text"
    default_str = format_decimal_with_commas(current_val)
    user_str = st.text_input(label, value=default_str, key=text_key, placeholder=placeholder)
    parsed = parse_decimal(user_str)
    # clamp to range
    if parsed < min_val:
        parsed = min_val
    if parsed > max_val:
        parsed = max_val
    st.session_state[key] = parsed
    return parsed

# -----------------------------------------------------------------------------
# Title / Subtitle
# -----------------------------------------------------------------------------
st.title(APP_TITLE)

# -----------------------------------------------------------------------------
# Onboarding / Inputs
# -----------------------------------------------------------------------------
if "setup_complete" not in st.session_state:
    st.session_state.setup_complete = False

def complete_setup():
    st.session_state.setup_complete = True

if not st.session_state.setup_complete:
    st.subheader("Data Nasabah & Rencana KPR (Kredit Pemilikan Rumah)", divider="rainbow")

    # Persist across reruns (numeric defaults as float)
    if "nama" not in st.session_state: st.session_state["nama"] = ""
    if "gaji_bersih" not in st.session_state: st.session_state["gaji_bersih"] = 0.0
    if "pengeluaran" not in st.session_state: st.session_state["pengeluaran"] = 0.0
    if "harga_properti" not in st.session_state: st.session_state["harga_properti"] = 0.0
    if "dp" not in st.session_state: st.session_state["dp"] = 0.0
    if "tenor_tahun" not in st.session_state: st.session_state["tenor_tahun"] = 15
    if "bunga_tahunan" not in st.session_state: st.session_state["bunga_tahunan"] = 10.0
    if "max_dsr" not in st.session_state: st.session_state["max_dsr"] = DEFAULT_MAX_DSR
    if "max_ltv" not in st.session_state: st.session_state["max_ltv"] = DEFAULT_MAX_LTV

    st.session_state["nama"] = st.text_input("Nama", value=st.session_state["nama"], placeholder="Nama lengkap")

    c1, c2 = st.columns(2)
    with c1:
        st.session_state["gaji_bersih"] = money_text_input(
            "Gaji Bersih Bulanan (IDR)", key="gaji_bersih", placeholder="contoh: 8,500,000"
        )
        st.session_state["harga_properti"] = money_text_input(
            "Harga Properti (IDR)", key="harga_properti", placeholder="contoh: 750,000,000"
        )
        # Tenor stays as integer number_input (clean and safe)
        st.session_state["tenor_tahun"] = st.number_input(
            "Tenor (tahun)", min_value=1, max_value=30, step=1, value=int(st.session_state["tenor_tahun"])
        )
    with c2:
        st.session_state["pengeluaran"] = money_text_input(
            "Total Pengeluaran Bulanan (IDR)", key="pengeluaran", placeholder="contoh: 3,000,000"
        )
        st.session_state["dp"] = money_text_input(
            "Uang Muka / DP (IDR)", key="dp", placeholder="contoh: 150,000,000"
        )
        st.session_state["bunga_tahunan"] = percent_text_input(
            "Bunga Tahunan (%)", key="bunga_tahunan", placeholder="contoh: 10.5", min_val=0.0, max_val=25.0
        )

    with st.expander("Kebijakan Perhitungan (opsional)"):
        cc1, cc2 = st.columns(2)
        with cc1:
            # keep slider for good UX; shows no trailing .0 due to formatting later
            st.session_state["max_dsr"] = st.slider(
                "Batas DSR (Debt Service Ratio)", 0.10, 0.70, float(st.session_state["max_dsr"]), 0.01
            )
        with cc2:
            st.session_state["max_ltv"] = st.slider(
                "Batas Maks LTV (Loan-to-Value)", 0.5, 1.0, float(st.session_state["max_ltv"]), 0.01
            )

    st.caption("**Catatan:** angka-angka ini simulasi dan dapat berbeda sesuai kebijakan bank & profil risiko nasabah.")
    st.button("Mulai Konsultasi", on_click=complete_setup, type="primary")

# -----------------------------------------------------------------------------
# Chat stage (Gemini) — only after setup
# -----------------------------------------------------------------------------
def monthly_payment(principal: float, annual_rate_pct: float, years: int) -> float:
    if principal <= 0 or years <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    n = years * 12
    if r == 0:
        return principal / n
    try:
        return principal * r / (1 - (1 + r) ** (-n))
    except ZeroDivisionError:
        return 0.0

def max_principal_from_dsr(net_income: float, expenses: float, dsr: float, annual_rate_pct: float, years: int) -> float:
    capacity = max(0.0, (net_income - expenses) * dsr)
    r = (annual_rate_pct / 100.0) / 12.0
    n = years * 12
    if r == 0:
        return capacity * n
    try:
        return capacity * (1 - (1 + r) ** (-n)) / r
    except ZeroDivisionError:
        return 0.0

def ensure_messages_initialized(sys_prompt: str, banker_context: str):
    if "messages" not in st.session_state:
        st.session_state.messages: List[dict] = []
        if banker_context.strip():
            st.session_state.messages.append({"role": "system", "content": banker_context.strip()})
        if sys_prompt.strip():
            st.session_state.messages.append({"role": "system", "content": sys_prompt.strip()})

if st.session_state.setup_complete:
    # Sidebar settings
    with st.sidebar:
        st.header("⚙️ Model Settings")
        model = st.selectbox("Model", [DEFAULT_MODEL, "gemini-1.5-flash", "gemini-1.5-pro"], index=0)
        temperature = st.slider("Temperature", 0.0, 1.0, DEFAULT_TEMPERATURE, 0.05)
        sys_prompt = st.text_area(
            "System prompt tambahan (opsional)",
            value="",
            height=90,
            help="Instruksi tambahan (opsional)."
        )
        reset_btn = st.button("Reset Percakapan 🗑️")

    # Resolve API key now
    google_api_key = resolve_google_api_key()
    if not google_api_key:
        st.error(
            "❌ Tidak ditemukan Google API Key.\n\n"
            "Tambahkan di file `.env` sebagai `GOOGLE_API_KEY=your-key`, "
            "set sebagai environment variable, atau taruh di `st.secrets`.\n\n"
            "Buat key di sini 👉 https://aistudio.google.com/api-keys"
        )
        st.stop()

    # Initialize LLM if config changed
    needs_reinit = (
        "llm" not in st.session_state
        or st.session_state.get("_last_key") != google_api_key
        or st.session_state.get("_last_model") != model
        or st.session_state.get("_last_temp") != temperature
    )
    if needs_reinit:
        st.session_state.llm = init_llm(google_api_key, model, temperature)
        st.session_state._last_key = google_api_key
        st.session_state._last_model = model
        st.session_state._last_temp = temperature

    # Reset conversation
    if reset_btn:
        st.session_state.pop("messages", None)
        st.rerun()

    # ------------------ Affordability math snapshot ------------------
    nama = st.session_state.get("nama", "").strip() or "Nasabah"
    gaji_bersih = float(st.session_state.get("gaji_bersih", 0.0))
    pengeluaran = float(st.session_state.get("pengeluaran", 0.0))
    harga = float(st.session_state.get("harga_properti", 0.0))
    dp = float(st.session_state.get("dp", 0.0))
    tenor = int(st.session_state.get("tenor_tahun", 1))
    bunga = float(st.session_state.get("bunga_tahunan", 0.0))
    max_dsr = float(st.session_state.get("max_dsr", DEFAULT_MAX_DSR))
    max_ltv = float(st.session_state.get("max_ltv", DEFAULT_MAX_LTV))

    need_loan = max(0.0, harga - dp)
    ltv = need_loan / harga if harga > 0 else 0.0
    pay_est = monthly_payment(need_loan, bunga, tenor)
    max_principal_dsr = max_principal_from_dsr(gaji_bersih, pengeluaran, max_dsr, bunga, tenor)
    dsr_used = (pay_est / max(1.0, gaji_bersih - pengeluaran)) if (gaji_bersih - pengeluaran) > 0 else 0.0

    # Display snapshot
    st.subheader("Ringkasan Simulasi", divider="rainbow")
    colA, colB, colC = st.columns(3)
    with colA:
        st.metric("Kebutuhan Pinjaman", rupiah(need_loan))
        st.metric("Angsuran / bulan (est.)", rupiah(pay_est))
    with colB:
        st.metric("DSR Terpakai (est.)", f"{dsr_used*100:,.0f}%")
        st.metric("Batas DSR", f"{max_dsr*100:,.0f}%")
    with colC:
        st.metric("LTV (pinjaman/harga)", f"{ltv*100:,.0f}%")
        st.metric("Batas LTV", f"{max_ltv*100:,.0f}%")

    # Compliance hints
    dsr_flag = dsr_used <= max_dsr if (gaji_bersih - pengeluaran) > 0 else False
    ltv_flag = ltv <= max_ltv if harga > 0 else True
    if not dsr_flag or not ltv_flag:
        st.warning(
            "⚠️ Catatan kelayakan awal:\n"
            f"- DSR terpenuhi: {'✅' if dsr_flag else '❌'}\n"
            f"- LTV dalam batas: {'✅' if ltv_flag else '❌'}",
            icon="⚠️",
        )

    # ------------------ Banker role system prompt ------------------
    banker_context = f"""
Anda adalah **Personal Banking Officer** berpengalaman yang membantu nasabah mengambil keputusan KPR secara bijak.
Berikan nasihat praktis dan bertanggung jawab, tekankan manajemen risiko, syarat pengajuan KPR.

Profil nasabah:
- Nama: {nama}
- Gaji bersih bulanan: {rupiah(gaji_bersih)}
- Total pengeluaran bulanan: {rupiah(pengeluaran)}
- Harga properti: {rupiah(harga)}
- DP: {rupiah(dp)}
- Tenor: {tenor} tahun
- Bunga: {format_decimal_with_commas(bunga)}% p.a.
- Batas DSR kebijakan: {max_dsr*100:,.0f}%
- Batas LTV kebijakan: {max_ltv*100:,.0f}%

Perhitungan awal:
- Kebutuhan pinjaman: {rupiah(need_loan)}
- Perkiraan angsuran/bulan: {rupiah(pay_est)}
- DSR terpakai (estimasi): {dsr_used*100:,.0f}%
- LTV: {ltv*100:,.0f}%
- Estimasi maksimum pokok pinjaman sesuai DSR: {rupiah(max_principal_dsr)}

Instruksi gaya & batasan:
- Gunakan bahasa Indonesia yang ramah, sopan, singkat, dan jelas dalam penyebutan nama nasabah.
- Tawarkan langkah-langkah konkret (contoh: tambah DP sekian, pilih tenor sekian, opsi fix-floating).
- Jangan memberikan janji persetujuan kredit.
- Jelaskan dalam proses pengajuan KPR histori SLIK OJK sangat berpengaruh.
- Jelaskan opsi (fixed vs floating, take over KPR, KPR syariah, penalty pelunasan, biaya-biaya).
- Sarankan pengumpulan dokumen dan pengecekan skor kredit bila relevan.
- Jika data kurang, ajukan pertanyaan klarifikasi satu per satu.
"""

    # Initialize messages once
    ensure_messages_initialized(sys_prompt=sys_prompt, banker_context=banker_context)

    # Render chat history (skip system messages)
    for msg in st.session_state.messages:
        if msg["role"] == "system":
            continue
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(msg["content"])

    # Resolve API key for chat
    google_api_key = resolve_google_api_key()
    if not google_api_key:
        st.stop()

    # Chat input
    user_text = st.chat_input("Tulis pertanyaan Anda tentang KPR…")
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        # Convert to LangChain messages
        lc_messages = []
        for m in st.session_state.messages:
            if m["role"] == "system":
                lc_messages.append(SystemMessage(content=m["content"]))
            elif m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            else:
                lc_messages.append(AIMessage(content=m["content"]))

        # Generate response
        try:
            with st.chat_message("assistant"):
                with st.spinner("Sedang menganalisis…"):
                    result = st.session_state.llm.invoke(lc_messages)
                    ai_text = getattr(result, "content", str(result))
                    st.markdown(ai_text)
            st.session_state.messages.append({"role": "assistant", "content": ai_text})
        except Exception as e:
            st.error(f"Error: {e}")