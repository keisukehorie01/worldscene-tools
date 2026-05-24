import base64
import json
import os
import re
import threading
import time
import uuid
import zipfile
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from flask import jsonify, request, send_file

from billing_sqlite import consume_credit, normalize_email, refund_credit


BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("PPT_RUNTIME_DIR", BASE_DIR / "runtime" / "ppt_jobs"))
UPLOAD_DIR = RUNTIME_DIR / "uploads"
OUTPUT_DIR = RUNTIME_DIR / "outputs"
JOB_DIR = RUNTIME_DIR / "jobs"

MAX_UPLOAD_BYTES = int(os.getenv("PPT_MAX_UPLOAD_BYTES", str(12 * 1024 * 1024)))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("PPT_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()

SLIDE_W = 9144000
SLIDE_H = 5143500

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def register_ppt_routes(app):
    ensure_runtime_dirs()

    @app.route("/api/ppt/jobs", methods=["POST"])
    def create_ppt_job():
      email = normalize_email(request.form.get("email", ""))
      if not email:
          return jsonify({"ok": False, "error": "email is required"}), 400

      if "image" not in request.files:
          return jsonify({"ok": False, "error": "image file is required"}), 400

      image = request.files["image"]
      if not image.filename:
          return jsonify({"ok": False, "error": "image filename is required"}), 400

      raw = image.read()
      if not raw:
          return jsonify({"ok": False, "error": "image file is empty"}), 400
      if len(raw) > MAX_UPLOAD_BYTES:
          return jsonify({"ok": False, "error": "image file is too large"}), 413

      mime_type = image.mimetype or "image/png"
      if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
          return jsonify({"ok": False, "error": "PNG, JPG, and WebP are supported"}), 400

      job_id = uuid.uuid4().hex
      try:
          consume_credit(email, job_id, amount=1)
      except ValueError:
          return jsonify({"ok": False, "error": "insufficient_credits"}), 402

      suffix = safe_suffix(image.filename, mime_type)
      upload_path = UPLOAD_DIR / f"{job_id}{suffix}"
      output_path = OUTPUT_DIR / f"{job_id}.pptx"
      upload_path.write_bytes(raw)

      job = {
          "id": job_id,
          "status": "queued",
          "progress": 5,
          "message": "Queued",
          "created_at": time.time(),
          "updated_at": time.time(),
          "input_filename": image.filename,
          "input_mime_type": mime_type,
          "input_path": str(upload_path),
          "output_path": str(output_path),
          "email": email,
          "credits_used": 1,
          "credit_refunded": False,
          "download_url": None,
          "error": None,
      }
      save_job(job)
      threading.Thread(target=process_job, args=(job_id,), daemon=True).start()

      return jsonify({"ok": True, "job": public_job(job)}), 202

    @app.route("/api/ppt/jobs/<job_id>", methods=["GET"])
    def get_ppt_job(job_id: str):
      job = load_job(job_id)
      if not job:
          return jsonify({"ok": False, "error": "job not found"}), 404
      return jsonify({"ok": True, "job": public_job(job)})

    @app.route("/api/ppt/jobs/<job_id>/download", methods=["GET"])
    def download_ppt_job(job_id: str):
      job = load_job(job_id)
      if not job:
          return jsonify({"ok": False, "error": "job not found"}), 404
      if job.get("status") != "completed":
          return jsonify({"ok": False, "error": "job is not completed"}), 409

      output_path = Path(job["output_path"])
      if not output_path.exists():
          return jsonify({"ok": False, "error": "output file is missing"}), 404

      return send_file(
          output_path,
          as_attachment=True,
          download_name="drop2ppt-editable.pptx",
          mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
      )


def ensure_runtime_dirs():
    for path in (UPLOAD_DIR, OUTPUT_DIR, JOB_DIR):
        path.mkdir(parents=True, exist_ok=True)


def safe_suffix(filename: str, mime_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return suffix
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(mime_type, ".img")


def save_job(job: Dict[str, Any]) -> None:
    job["updated_at"] = time.time()
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    (JOB_DIR / f"{job['id']}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def load_job(job_id: str) -> Optional[Dict[str, Any]]:
    with JOBS_LOCK:
        if job_id in JOBS:
            return JOBS[job_id]

    path = JOB_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job


def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "download_url": f"/api/ppt/jobs/{job['id']}/download" if job.get("status") == "completed" else None,
        "error": job.get("error"),
    }


def update_job(job_id: str, **changes) -> Dict[str, Any]:
    job = load_job(job_id)
    if not job:
        raise RuntimeError(f"job not found: {job_id}")
    job.update(changes)
    save_job(job)
    return job


def process_job(job_id: str) -> None:
    try:
        job = update_job(job_id, status="processing", progress=20, message="Analyzing image")
        image_path = Path(job["input_path"])
        image_bytes = image_path.read_bytes()
        mime_type = job["input_mime_type"]

        analysis = analyze_image_for_ppt(image_bytes, mime_type)
        update_job(job_id, progress=70, message="Rebuilding editable slide")

        output_path = Path(job["output_path"])
        write_pptx(output_path, analysis)
        update_job(job_id, status="completed", progress=100, message="Ready to download")
    except Exception as exc:
        job = load_job(job_id)
        if job and job.get("email") and not job.get("credit_refunded"):
            refund_credit(job["email"], job_id, amount=int(job.get("credits_used") or 1))
            update_job(job_id, credit_refunded=True)
        update_job(job_id, status="failed", progress=100, message="Conversion failed", error=str(exc))


def analyze_image_for_ppt(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        return fallback_analysis()

    prompt = """
You convert visual drafts into editable PowerPoint structure.

Analyze the image and return only valid JSON. Do not wrap it in Markdown.
Use this schema:
{
  "title": "short slide title",
  "subtitle": "short slide subtitle",
  "summary": "one sentence answer describing the slide",
  "sections": [
    {
      "title": "section title",
      "body": "1-2 short lines",
      "x": 0.05,
      "y": 0.18,
      "w": 0.28,
      "h": 0.18
    }
  ],
  "steps": [
    {"label": "1", "title": "Upload", "body": "short body"}
  ]
}

Coordinates are normalized 0..1 relative to a 16:9 slide.
Return 4 to 10 sections, prioritizing readable editable content over pixel-perfect recreation.
Keep all text concise.
""".strip()

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ]
    }
    response = requests.post(url, json=body, timeout=90)
    response.raise_for_status()
    data = response.json()
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    text = "".join(part.get("text", "") for part in parts)
    parsed = parse_json_from_model(text)
    return normalize_analysis(parsed)


def parse_json_from_model(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def normalize_analysis(raw: Dict[str, Any]) -> Dict[str, Any]:
    analysis = fallback_analysis()
    analysis["title"] = clean_text(raw.get("title")) or analysis["title"]
    analysis["subtitle"] = clean_text(raw.get("subtitle")) or analysis["subtitle"]
    analysis["summary"] = clean_text(raw.get("summary")) or analysis["summary"]

    sections = []
    for item in raw.get("sections") or []:
        if not isinstance(item, dict):
            continue
        sections.append({
            "title": clean_text(item.get("title")) or "Section",
            "body": clean_text(item.get("body")) or "",
            "x": clamp_float(item.get("x"), 0.05, 0.86),
            "y": clamp_float(item.get("y"), 0.18, 0.78),
            "w": clamp_float(item.get("w"), 0.18, 0.40),
            "h": clamp_float(item.get("h"), 0.12, 0.22),
        })
    if sections:
        analysis["sections"] = sections[:10]

    steps = []
    for item in raw.get("steps") or []:
        if not isinstance(item, dict):
            continue
        steps.append({
            "label": clean_text(item.get("label")) or str(len(steps) + 1),
            "title": clean_text(item.get("title")) or "Step",
            "body": clean_text(item.get("body")) or "",
        })
    if steps:
        analysis["steps"] = steps[:5]

    return analysis


def fallback_analysis() -> Dict[str, Any]:
    return {
        "title": "Image to Editable PowerPoint",
        "subtitle": "Editable reconstruction draft",
        "summary": "This beta output creates editable text and layout blocks from an uploaded visual draft.",
        "sections": [
            {"title": "Source image", "body": "Uploaded visual draft", "x": 0.05, "y": 0.22, "w": 0.26, "h": 0.18},
            {"title": "Layout", "body": "Main panels and hierarchy", "x": 0.37, "y": 0.22, "w": 0.26, "h": 0.18},
            {"title": "Editable text", "body": "Slide text can be revised", "x": 0.69, "y": 0.22, "w": 0.26, "h": 0.18},
            {"title": "PowerPoint", "body": "Generated as PPTX", "x": 0.21, "y": 0.52, "w": 0.26, "h": 0.18},
            {"title": "Delivery", "body": "Ready for human cleanup", "x": 0.53, "y": 0.52, "w": 0.26, "h": 0.18},
        ],
        "steps": [
            {"label": "1", "title": "Upload", "body": "Drop an image"},
            {"label": "2", "title": "Analyze", "body": "Read the layout"},
            {"label": "3", "title": "Rebuild", "body": "Create editable objects"},
            {"label": "4", "title": "Download", "body": "Get a PPTX file"},
        ],
    }


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:180]


def clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, number))


def write_pptx(path: Path, analysis: Dict[str, Any]) -> None:
    slide_xml = build_slide_xml(analysis)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", content_types_xml())
        pptx.writestr("_rels/.rels", package_rels_xml())
        pptx.writestr("docProps/core.xml", core_props_xml())
        pptx.writestr("docProps/app.xml", app_props_xml())
        pptx.writestr("ppt/presentation.xml", presentation_xml())
        pptx.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml())
        pptx.writestr("ppt/slides/slide1.xml", slide_xml)
        pptx.writestr("ppt/slides/_rels/slide1.xml.rels", empty_rels_xml())
        pptx.writestr("ppt/slideMasters/slideMaster1.xml", slide_master_xml())
        pptx.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels_xml())
        pptx.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml())
        pptx.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", empty_rels_xml())
        pptx.writestr("ppt/theme/theme1.xml", theme_xml())


def build_slide_xml(analysis: Dict[str, Any]) -> str:
    shapes = [
        shape_xml(2, 0, 0, SLIDE_W, SLIDE_H, "", "", fill="10233F", line="10233F", font="FFFFFF", font_size=1200),
        textbox_xml(3, 420000, 260000, 8300000, 700000, analysis["title"], "FFFFFF", 3400, bold=True),
        textbox_xml(4, 470000, 940000, 8000000, 360000, analysis["subtitle"], "D9F3FF", 1350, bold=False),
        textbox_xml(5, 500000, 4480000, 8100000, 360000, analysis["summary"], "EAF7FF", 1100, bold=False),
    ]
    shape_id = 10
    for section in analysis["sections"]:
        x = int(section["x"] * SLIDE_W)
        y = int(section["y"] * SLIDE_H)
        w = int(section["w"] * SLIDE_W)
        h = int(section["h"] * SLIDE_H)
        shapes.append(shape_xml(shape_id, x, y, w, h, section["title"], section["body"]))
        shape_id += 1

    step_w = int(SLIDE_W * 0.20)
    gap = int(SLIDE_W * 0.02)
    start_x = int(SLIDE_W * 0.08)
    y = int(SLIDE_H * 0.76)
    for index, step in enumerate(analysis["steps"][:4]):
        x = start_x + index * (step_w + gap)
        title = f"{step['label']}  {step['title']}"
        shapes.append(shape_xml(shape_id, x, y, step_w, int(SLIDE_H * 0.14), title, step["body"], fill="E9F7F7", line="1AA6D9", font="12324A"))
        shape_id += 1

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      {''.join(shapes)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def shape_xml(shape_id: int, x: int, y: int, w: int, h: int, title: str, body: str, fill: str = "123B59", line: str = "1AA6D9", font: str = "FFFFFF", font_size: int = 1050) -> str:
    text = ""
    if title or body:
        text = f"""
      <p:txBody>
        <a:bodyPr wrap="square" lIns="120000" tIns="90000" rIns="120000" bIns="90000"/>
        <a:lstStyle/>
        <a:p><a:r><a:rPr lang="en-US" sz="{font_size + 250}" b="1"><a:solidFill><a:srgbClr val="{font}"/></a:solidFill></a:rPr><a:t>{escape(title)}</a:t></a:r></a:p>
        <a:p><a:r><a:rPr lang="en-US" sz="{font_size}"><a:solidFill><a:srgbClr val="{font}"/></a:solidFill></a:rPr><a:t>{escape(body)}</a:t></a:r></a:p>
      </p:txBody>"""
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{shape_id}" name="Editable block {shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>
          <a:solidFill><a:srgbClr val="{fill}"><a:alpha val="90000"/></a:srgbClr></a:solidFill>
          <a:ln w="18000"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>
        </p:spPr>
        {text}
      </p:sp>"""


def textbox_xml(shape_id: int, x: int, y: int, w: int, h: int, text: str, font: str, font_size: int, bold: bool = False) -> str:
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{shape_id}" name="Editable text {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
          <a:noFill/>
        </p:spPr>
        <p:txBody>
          <a:bodyPr wrap="square"/>
          <a:lstStyle/>
          <a:p><a:r><a:rPr lang="en-US" sz="{font_size}" b="{1 if bold else 0}"><a:solidFill><a:srgbClr val="{font}"/></a:solidFill></a:rPr><a:t>{escape(text)}</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>"""


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>"""


def package_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def presentation_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
  <p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""


def presentation_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
</Relationships>"""


def empty_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""


def slide_master_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>"""


def slide_master_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>"""


def slide_layout_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>"""


def theme_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Drop2PPT">
  <a:themeElements>
    <a:clrScheme name="Drop2PPT"><a:dk1><a:srgbClr val="14212F"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="12324A"/></a:dk2><a:lt2><a:srgbClr val="F2F6F8"/></a:lt2><a:accent1><a:srgbClr val="0F8D80"/></a:accent1><a:accent2><a:srgbClr val="1AA6D9"/></a:accent2><a:accent3><a:srgbClr val="D09B24"/></a:accent3><a:accent4><a:srgbClr val="D35C43"/></a:accent4><a:accent5><a:srgbClr val="516173"/></a:accent5><a:accent6><a:srgbClr val="10233F"/></a:accent6><a:hlink><a:srgbClr val="1AA6D9"/></a:hlink><a:folHlink><a:srgbClr val="0F8D80"/></a:folHlink></a:clrScheme>
    <a:fontScheme name="Office"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Office"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme>
  </a:themeElements>
</a:theme>"""


def core_props_xml() -> str:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Drop2PPT editable slide</dc:title>
  <dc:creator>WorldScene</dc:creator>
  <cp:lastModifiedBy>WorldScene</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>"""


def app_props_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>WorldScene Drop2PPT</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>1</Slides>
</Properties>"""
