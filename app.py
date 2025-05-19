import os
import re
import fitz
import pytesseract
import tempfile
from flask import Flask, request, render_template
from PIL import Image
from werkzeug.utils import secure_filename

app = Flask(__name__)
pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# Health Metrics dictionary: metric -> [(age_min, age_max, low, high, unit), ...]
HEALTH_METRICS = {
    "Hemoglobin": [(0, 99, 12, 16, "g/dL")],
    "WBC": [(0, 99, 4000, 11000, "cells/uL")],
    "RBC": [(0, 99, 4.7, 6.1, "million/uL")],
    "Platelet": [(0, 99, 150000, 450000, "cells/uL")],
    "Glucose (Fasting)": [(0, 99, 70, 100, "mg/dL")],
    "Glucose (Postprandial)": [(0, 99, 70, 140, "mg/dL")],
    "Cholesterol (Total)": [(0, 99, 125, 200, "mg/dL")],
    "LDL Cholesterol": [(0, 99, 0, 100, "mg/dL")],
    "HDL Cholesterol": [(0, 99, 40, 60, "mg/dL")],
    "Triglycerides": [(0, 99, 0, 150, "mg/dL")],
    "Blood Pressure (Systolic)": [(0, 99, 90, 120, "mmHg")],
    "Blood Pressure (Diastolic)": [(0, 99, 60, 80, "mmHg")],
    "Heart Rate": [(0, 99, 60, 100, "bpm")],
    "BMI": [(0, 99, 18.5, 24.9, "")],
    "Creatinine": [(0, 99, 0.6, 1.2, "mg/dL")],
    "Urea": [(0, 99, 7, 20, "mg/dL")],
    "ALT (SGPT)": [(0, 99, 0, 40, "U/L")],
    "AST (SGOT)": [(0, 99, 0, 40, "U/L")],
    "Bilirubin (Total)": [(0, 99, 0.1, 1.2, "mg/dL")],
    "Bilirubin (Direct)": [(0, 99, 0, 0.3, "mg/dL")],
    "Calcium": [(0, 99, 8.5, 10.5, "mg/dL")],
    "Iron": [(0, 99, 60, 170, "mcg/dL")],
    "Vitamin B12": [(0, 99, 190, 950, "pg/mL")],
    "Vitamin D": [(0, 99, 20, 50, "ng/mL")],
    "TSH": [(0, 99, 0.4, 4.0, "mIU/L")],
    "Free T4": [(0, 99, 0.8, 1.8, "ng/dL")],
    "Free T3": [(0, 99, 2.3, 4.2, "pg/mL")],
    "CRP": [(0, 99, 0, 10, "mg/L")],
    "ESR": [(0, 99, 0, 20, "mm/hr")],
    "Sodium": [(0, 99, 135, 145, "mmol/L")],
    "Potassium": [(0, 99, 3.5, 5.0, "mmol/L")],
    "Chloride": [(0, 99, 96, 106, "mmol/L")],
    "Magnesium": [(0, 99, 1.7, 2.2, "mg/dL")],
    "Phosphorus": [(0, 99, 2.5, 4.5, "mg/dL")],
    "Albumin": [(0, 99, 3.5, 5.0, "g/dL")],
    "Total Protein": [(0, 99, 6.0, 8.3, "g/dL")],
    "Alkaline Phosphatase": [(0, 99, 44, 147, "U/L")],
    "LDH": [(0, 99, 140, 280, "U/L")],
    "Amylase": [(0, 99, 30, 110, "U/L")],
    "Lipase": [(0, 99, 0, 160, "U/L")],
    "GGT": [(0, 99, 9, 48, "U/L")],
    "Ferritin": [(0, 99, 24, 336, "ng/mL")],
    "Hemoglobin A1c": [(0, 99, 4.0, 5.6, "%")],
    "Uric Acid": [(0, 99, 3.5, 7.2, "mg/dL")],
    "CK-MB": [(0, 99, 0, 5, "ng/mL")],
    "Troponin I": [(0, 99, 0, 0.04, "ng/mL")],
    "Fibrinogen": [(0, 99, 200, 400, "mg/dL")],
    "Prothrombin Time": [(0, 99, 11, 13.5, "seconds")],
    "INR": [(0, 99, 0.8, 1.2, "")],
    # Add more metrics if needed
}

def extract_health_data(text):
    abnormal_data = []
    normal_data = []
    normal = True
    found_any_metric = False

    # Preprocess text to handle common variations
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    text = text.lower()  # Convert to lowercase for case-insensitive matching

    for metric, ranges in HEALTH_METRICS.items():
        # Each metric may have multiple age-range tuples, but here we ignore age and take first range for simplicity
        low, high, unit = ranges[0][2], ranges[0][3], ranges[0][4]
        
        # Create a more flexible pattern that handles common variations
        metric_pattern = re.escape(metric.lower())
        # Allow for common variations in how numbers might appear
        pattern = rf"{metric_pattern}.*?(\d+[.,]?\d*)"
        match = re.search(pattern, text)
        
        if match:
            found_any_metric = True
            # Clean and convert the matched value
            value_str = match.group(1).replace(',', '.')
            try:
                value = float(value_str)
                if value < low:
                    abnormal_data.append(f"{metric}: {value} {unit} (Low)")
                    normal = False
                elif value > high:
                    abnormal_data.append(f"{metric}: {value} {unit} (High)")
                    normal = False
                else:
                    normal_data.append(f"{metric}: {value} {unit} (Normal)")
            except ValueError:
                continue  # Skip if value can't be converted to float
    
    if not found_any_metric:
        # Try to find any numbers in the text as a fallback
        numbers = re.findall(r'\d+[.,]?\d*', text)
        if numbers:
            return "Found numbers in the report but couldn't match them to specific health metrics. Please check if this is a health report."
        return "This does not appear to be a health report."
    
    summary_text = "Report Status: Normal" if normal else "Report Status: Abnormal"
    return '\n'.join(abnormal_data + normal_data) + "\n\n" + summary_text

def extract_text_from_pdf(file_path):
    text = ""
    doc = fitz.open(file_path)
    for page in doc:
        text += page.get_text("text")
    if not text.strip():
        # OCR fallback
        for page in doc:
            pix = page.get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text += pytesseract.image_to_string(img)
    return extract_health_data(text)

def extract_text_from_image(file_path):
    image = Image.open(file_path)
    text = pytesseract.image_to_string(image)
    return extract_health_data(text)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["report"]
        if file:
            filename = secure_filename(file.filename)
            _, ext = os.path.splitext(filename)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                file.save(tmp.name)
                if ext.lower() == ".pdf":
                    summary = extract_text_from_pdf(tmp.name)
                else:
                    summary = extract_text_from_image(tmp.name)
                # Optionally delete tmp file here
                # os.unlink(tmp.name)
                return render_template("result.html", summary=summary)
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
