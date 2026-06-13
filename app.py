from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict

import streamlit as st
from PIL import Image, ImageChops

from storage import DATA_DIR, OUTPUT_DIR, add_history_record, init_db, list_history, load_profile, save_profile
from timesheet_engine import (
    DAYS,
    format_week_range,
    generate_timesheet_files,
    load_overlay_config,
    monday_for_date,
    reset_overlay_config,
    save_overlay_config,
    week_dates_from_monday,
)

APP_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = APP_DIR / "template.pdf"
SIGNATURE_PATH = APP_DIR / "employee_signature.png"

DAY_LABELS = {
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}


def save_uploaded_file(uploaded_file, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return destination


def find_saved_signature() -> Path | None:
    return SIGNATURE_PATH if SIGNATURE_PATH.exists() else None



def _trim_transparent_edges(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img



def _remove_background(img: Image.Image, threshold: int = 238, softness: int = 25) -> Image.Image:
    img = img.convert("RGBA")
    pixels = img.load()
    width, height = img.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            brightness = (r + g + b) / 3
            min_channel = min(r, g, b)
            max_channel = max(r, g, b)
            if brightness >= threshold and (max_channel - min_channel) < 40:
                pixels[x, y] = (255, 255, 255, 0)
            elif brightness >= threshold - softness:
                new_alpha = max(0, min(255, int((threshold - brightness) / softness * 255)))
                pixels[x, y] = (r, g, b, min(a, new_alpha))
    return img



def process_signature(uploaded_file, remove_background: bool = True, trim_edges: bool = True) -> Path:
    try:
        img = Image.open(uploaded_file)
    except Exception as exc:
        raise ValueError("Unsupported signature file. Please upload an image file.") from exc

    img = img.convert("RGBA")
    if remove_background:
        img = _remove_background(img)
    if trim_edges:
        img = _trim_transparent_edges(img)

    # Ensure a little padding so the signature does not touch the edges.
    bg = Image.new("RGBA", (img.width + 24, img.height + 16), (255, 255, 255, 0))
    bg.paste(img, (12, 8), img)
    bg.save(SIGNATURE_PATH)
    return SIGNATURE_PATH



def get_payload_defaults(history_payload: Dict[str, Any] | None, profile: Dict[str, Any]) -> Dict[str, Any]:
    if history_payload:
        return history_payload

    today_monday = monday_for_date(date.today())
    week_dates = week_dates_from_monday(today_monday)
    return {
        "employee_name": profile.get("employee_name", ""),
        "supervisor_name": profile.get("supervisor_name", ""),
        "week_monday": today_monday.isoformat(),
        "reporting_week": format_week_range(today_monday),
        "dates": {day: week_dates[day].strftime("%m/%d/%Y") for day in DAYS},
        "hours": {
            "monday": 8.0,
            "tuesday": 8.0,
            "wednesday": 8.0,
            "thursday": 8.0,
            "friday": 8.0,
            "saturday": 0.0,
            "sunday": 0.0,
        },
    }



def render_history_loader() -> Dict[str, Any] | None:
    history = list_history(limit=50)
    if not history:
        return None

    options = {"Start new timesheet": None}
    for item in history:
        label = f"{item['reporting_week']} - {item['employee_name']} - {item['total_hours']} hrs"
        options[label] = item

    selected_label = st.sidebar.selectbox("Edit / regenerate previous week", list(options.keys()))
    selected = options[selected_label]
    if not selected:
        return None

    try:
        return json.loads(selected.get("payload_json", "{}"))
    except json.JSONDecodeError:
        st.sidebar.warning("Could not load the saved data for this history item.")
        return None



def read_file_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()



def main() -> None:
    st.set_page_config(page_title="USK Timesheet Generator", page_icon="🧾", layout="wide")
    init_db()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    st.title("USK Systems IT INC Timesheet Generator")
    st.caption("Upload the original PDF template once, enter the week and hours, then generate a submission-ready PDF.")

    profile = load_profile()
    selected_history_payload = render_history_loader()
    defaults = get_payload_defaults(selected_history_payload, profile)

    with st.sidebar:
        st.header("Template Setup")
        template_upload = st.file_uploader("Upload original USK timesheet PDF", type=["pdf"])
        if template_upload:
            save_uploaded_file(template_upload, TEMPLATE_PATH)
            st.success("Template saved. The app will reuse this PDF every week.")

        if TEMPLATE_PATH.exists():
            st.success("Template is ready.")
        else:
            st.error("Upload the original PDF template before generating a timesheet.")

        st.divider()
        st.header("Saved Signature")
        st.caption("Accepted formats: PNG, JPG, JPEG, WEBP, BMP, TIFF and most common image formats.")
        remove_bg = st.checkbox("Remove signature background", value=True)
        trim_edges = st.checkbox("Trim empty margins around signature", value=True)
        signature_upload = st.file_uploader("Upload / replace employee signature", type=None)
        if signature_upload:
            try:
                process_signature(signature_upload, remove_background=remove_bg, trim_edges=trim_edges)
                st.success("Employee signature saved for future weeks.")
            except Exception as exc:
                st.error(str(exc))

        saved_signature = find_saved_signature()
        if saved_signature and saved_signature.exists():
            try:
                st.image(Image.open(saved_signature), caption="Saved employee signature preview", width=220)
            except Exception:
                st.info("Signature file is saved.")

            if st.button("Remove saved signature"):
                saved_signature.unlink(missing_ok=True)
                st.success("Saved signature removed.")
                st.rerun()
        else:
            st.info("No employee signature saved yet. You can still generate the PDF without it.")

    with st.expander("Advanced: adjust overlay positions", expanded=False):
        st.write("Use this only if the text is slightly off. The original PDF is still used as the background.")
        config = load_overlay_config()
        config_text = st.text_area("Overlay configuration JSON", json.dumps(config, indent=2), height=260)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Save overlay config"):
                try:
                    save_overlay_config(json.loads(config_text))
                    st.success("Overlay config saved.")
                except json.JSONDecodeError as exc:
                    st.error(f"Invalid JSON: {exc}")
        with col_b:
            if st.button("Reset overlay config"):
                reset_overlay_config()
                st.success("Overlay config reset to default. Refresh the page to view it.")

    st.subheader("Timesheet Details")
    col1, col2 = st.columns(2)
    with col1:
        employee_name = st.text_input("Employee Name", value=defaults.get("employee_name", ""))
    with col2:
        supervisor_name = st.text_input("Supervisor Name", value=defaults.get("supervisor_name", ""))

    default_week_str = defaults.get("week_monday")
    try:
        default_week = date.fromisoformat(default_week_str) if default_week_str else monday_for_date(date.today())
    except ValueError:
        default_week = monday_for_date(date.today())

    selected_monday = st.date_input("Reporting Week - Monday", value=default_week)
    week_dates = week_dates_from_monday(selected_monday)
    auto_reporting_week = format_week_range(selected_monday)

    reporting_week = st.text_input("Reporting Week", value=defaults.get("reporting_week") or auto_reporting_week)
    if selected_monday != default_week and reporting_week == defaults.get("reporting_week"):
        reporting_week = auto_reporting_week
        st.info(f"Reporting week updated to {reporting_week}")

    st.subheader("Dates")
    date_defaults = defaults.get("dates", {})
    date_values: Dict[str, str] = {}
    date_cols = st.columns(7)
    for i, day in enumerate(DAYS):
        auto_value = week_dates[day].strftime("%m/%d/%Y")
        default_value = date_defaults.get(day, auto_value)
        if selected_monday != default_week:
            default_value = auto_value
        with date_cols[i]:
            date_values[day] = st.text_input(DAY_LABELS[day], value=default_value, key=f"date_{day}")

    st.subheader("Hours Worked")
    hour_defaults = defaults.get("hours", {})
    hours: Dict[str, float] = {}
    hour_cols = st.columns(7)
    for i, day in enumerate(DAYS):
        default_hour = float(hour_defaults.get(day, 0.0) or 0.0)
        with hour_cols[i]:
            hours[day] = st.number_input(
                DAY_LABELS[day],
                min_value=0.0,
                max_value=24.0,
                value=default_hour,
                step=0.25,
                key=f"hours_{day}",
            )

    total_hours = round(sum(hours.values()), 2)
    st.metric("Total Hours", f"{total_hours:g}")

    save_recurring = st.checkbox("Save employee and supervisor details for future weeks", value=True)

    payload = {
        "employee_name": employee_name.strip(),
        "supervisor_name": supervisor_name.strip(),
        "week_monday": selected_monday.isoformat(),
        "reporting_week": reporting_week.strip() or auto_reporting_week,
        "dates": date_values,
        "hours": hours,
        "total_hours": total_hours,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    can_generate = TEMPLATE_PATH.exists() and bool(employee_name.strip()) and bool(supervisor_name.strip())

    st.divider()
    generate_col, download_col = st.columns([1, 2])
    with generate_col:
        generate_clicked = st.button("Generate PDF", type="primary", disabled=not can_generate)

    if not can_generate:
        st.warning("Add the template PDF, Employee Name, and Supervisor Name to enable generation.")

    if generate_clicked:
        if save_recurring:
            save_profile({"employee_name": employee_name.strip(), "supervisor_name": supervisor_name.strip()})

        signature_path = find_saved_signature()
        try:
            pdf_path, docx_path = generate_timesheet_files(
                template_pdf=TEMPLATE_PATH,
                output_dir=OUTPUT_DIR,
                payload=payload,
                signature_image=signature_path,
            )
            add_history_record(
                reporting_week=payload["reporting_week"],
                employee_name=payload["employee_name"],
                supervisor_name=payload["supervisor_name"],
                total_hours=payload["total_hours"],
                pdf_path=pdf_path,
                docx_path=docx_path,
                payload=payload,
            )
            st.session_state["last_pdf"] = str(pdf_path)
            st.session_state["last_docx"] = str(docx_path)
            st.success("Timesheet generated successfully.")
        except Exception as exc:
            st.error(f"Could not generate the timesheet: {exc}")

    with download_col:
        last_pdf = Path(st.session_state.get("last_pdf", "")) if st.session_state.get("last_pdf") else None
        last_docx = Path(st.session_state.get("last_docx", "")) if st.session_state.get("last_docx") else None

        if last_pdf and last_pdf.exists():
            st.download_button(
                "Download PDF",
                data=read_file_bytes(last_pdf),
                file_name=last_pdf.name,
                mime="application/pdf",
            )
        if last_docx and last_docx.exists():
            st.download_button(
                "Download Word",
                data=read_file_bytes(last_docx),
                file_name=last_docx.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    st.divider()
    st.subheader("History")
    history = list_history(limit=25)
    if not history:
        st.info("No generated timesheets yet.")
    else:
        for item in history[:10]:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 2, 1, 2])
                c1.write(f"**Week:** {item['reporting_week']}")
                c2.write(f"**Employee:** {item['employee_name']}")
                c3.write(f"**Hours:** {item['total_hours']:g}")
                c4.write(f"**Created:** {item['created_at']}")

                pdf_path = Path(item["pdf_path"])
                docx_path = Path(item["docx_path"])
                d1, d2 = st.columns(2)
                if pdf_path.exists():
                    d1.download_button(
                        "Download PDF",
                        data=read_file_bytes(pdf_path),
                        file_name=pdf_path.name,
                        mime="application/pdf",
                        key=f"hist_pdf_{item['id']}",
                    )
                if docx_path.exists():
                    d2.download_button(
                        "Download Word",
                        data=read_file_bytes(docx_path),
                        file_name=docx_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"hist_docx_{item['id']}",
                    )


if __name__ == "__main__":
    main()
