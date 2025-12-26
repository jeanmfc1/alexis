# ALEXIS/policy/ta_policy.py

from __future__ import annotations
import re

# Therapeutic area labels
TA_ONCOLOGY = "Oncology"
TA_INFECTIOUS = "Infectious Disease"
TA_IMMUNO = "Immunology / Inflammation"
TA_NEURO = "Neurology / CNS"
TA_CARDIO = "Cardiovascular"
TA_METABOLIC = "Metabolic / Endocrine"
TA_RARE = "Rare / Genetic"
TA_MSK = "Musculoskeletal"
TA_OTHER = "Other"

# Benign guard for oncology phrases in non-disease contexts
BENIGN_GUARD_KWS = ["screening", "registry", "survey", "questionnaire", "validation"]

# Keyword sets
ONCOLOGY_KW = [
    "cancer", "oncology", "tumor", "tumour", "carcinoma", "sarcoma", "lymphoma",
    "leukemia", "leukaemia", "myeloma", "metastatic", "metastasis", "metastases",
    "carcinomatosis", "solid tumor", "solid tumour", "neoplasm",
    "glioma", "glioblastoma", "gbm", "medulloblastoma", "ependymoma", "astrocytoma",
    "high grade glioma", "malignant glioma", "melanoma",
    "malignancy", "malignancies", "malignant neoplasm", "malignant",
    "hematologic malignancy", "hematological malignancy",
    "hematologic malignancies", "hematological malignancies",
    "b-cell malignancy", "b cell malignancy", "t-cell malignancy", "t cell malignancy", "blood cancer",
]
INFECTIOUS_KW = [
    "infectious", "infection", "viral", "virus", "bacterial", "bacteria",
    "fungal", "fungus", "hiv", "covid", "sars-cov-2", "influenza", "flu",
    "hepatitis", "tuberculosis", "tuberculous", "malaria", "antiviral",
    "antimicrobial", "antibiotic", "sepsis", "pneumonia", "vaccine", "vaccination",
]
IMMUNO_KW = [
    "autoimmune", "inflammation", "inflammatory", "immune", "immuno",
    "lupus", "sle", "rheumatoid", "arthritis", "psoriasis",
    "eczema", "atopic dermatitis", "crohn", "crohn's", "ulcerative colitis",
    "ibd", "asthma", "multiple sclerosis", "ms ", "myasthenia gravis", "ocular myasthenia gravis", "gmg",
]
NEURO_KW = [
    "neurology", "neurologic", "neurological", "cns", "brain", "spinal",
    "alzheimer", "parkinson", "dementia", "neurodegenerative", "epilepsy", "seizure",
    "migraine", "depression", "schizophrenia", "bipolar", "psychiatric", "autism", "adhd",
    # neuro rehab/outcomes for stroke carveout
    "aphasia", "hemiparesis", "motor recovery", "cognitive impairment", "rehabilitation",
]
CARDIO_KW = [
    "cardiovascular", "cardiac", "heart", "myocardial", "coronary",
    "arrhythmia", "atrial fibrillation", "hypertension", "stroke", "thrombosis", "heart failure",
    "aortic valve", "mitral valve", "tricuspid valve", "pulmonary valve",
    "aortic stenosis", "aortic regurgitation", "mitral regurgitation",
    "valve disease", "valve stenosis", "valve regurgitation", "transcatheter aortic valve",
    "tavr", "tavi", "transfemoral", "valve replacement",
    "pacing", "conduction system pacing", "left bundle branch", "bundle branch block",
    "pacemaker", "implantable cardioverter defibrillator", "icd", "defibrillator",
    "catheter ablation", "heart catheterization", "cardiac catheterization", "pci", "angioplasty",
    "cabg", "endarterectomy", "carotid",
    "pulmonary hypertension", "pulmonary artery hypertension",
    "ptca", "balloon catheter", "drug-coated balloon", "dcb",
    "aneurysm",
]
METABOLIC_KW = [
    "metabolic", "endocrine", "diabetes", "diabetic", "obesity", "insulin",
    "lipid", "cholesterol", "dyslipidemia", "thyroid", "hyperthyroid",
    "hypothyroid", "metabolic syndrome", "fatty liver", "nafld", "nash",
]
RARE_KW = [
    "rare disease", "orphan", "genetic", "inherited", "deficiency",
    "lysosomal", "dystrophy", "fragile x", "cystic fibrosis", "spinal muscular atrophy",
]
MSK_KW = [
    "osteoarthritis", "musculoskeletal", "low back pain", "back pain",
    "myofascial pain", "hip osteoarthritis", "knee osteoarthritis",
    "arthroplasty", "hip arthroplasty", "knee arthroplasty", "total knee arthroplasty", "total hip arthroplasty", "subacromial",
    "patellofemoral", "patello femoral", "anterior knee pain", "popliteus",
]

# Pain patterns
PAIN_SYNDROME_PATS = [
    re.compile(r"\bchronic pain\b"),
    re.compile(r"\blow back pain\b"),
    re.compile(r"\bback pain\b"),
    re.compile(r"\bmyofascial pain\b"),
    re.compile(r"\bfibromyalgia\b"),
    re.compile(r"\bpain syndrome\b"),
    re.compile(r"\bcomplex regional pain syndrome\b"),
    re.compile(r"\bcrps\b"),
]
PDPN_PATS = [
    re.compile(r"\bpainful diabetic peripheral neuropathy\b"),
    re.compile(r"\bdiabetic peripheral neuropathy\b"),
    re.compile(r"\bdiabetic neuropathic pain\b"),
    re.compile(r"\bpdpn\b"),
    re.compile(r"\bpdnp\b"),
]

# Device/catheter/valve guards
NON_CARDIO_CATHETER_EXCLUSIONS = [
    "pleural catheter", "urethral catheter", "central venous catheter",
    "venous catheter", "dialysis catheter", "peritoneal catheter", "epidural catheter",
]
CARDIO_CATHETER_CONTEXT = [
    "atrial fibrillation", "af", "ablation", "electrophysi", "pacing", "conduction",
    "left bundle", "bundle branch", "cardiac", "coronary", "aortic", "mitral", "tricuspid", "pulmonary",
    "ptca", "angioplasty", "drug-coated balloon", "dcb",
    "heart catheterization", "cardiac catheterization",
    "pulmonary artery hypertension", "pulmonary hypertension",
]
NON_CARDIAC_VALVE_EXCLUSIONS = ["passy-muir valve", "tracheostomy", "speaking valve"]

CARDIAC_VALVE_CONTEXT = [
    "aortic valve", "mitral valve", "tricuspid valve", "pulmonary valve",
    "aortic stenosis", "aortic regurgitation", "mitral regurgitation",
    "valve stenosis", "valve regurgitation", "valve disease", "transcatheter aortic valve",
]
CARDIO_STENT_CONTEXT = ["coronary", "cardiac", "pci", "angioplasty", "aortic", "carotid", "tavr", "tavi"]

# Stroke detection terms for audit use
STROKE_PATS = [
    re.compile(r"\bstroke\b"),
    re.compile(r"\btia\b"),
    re.compile(r"\btransient ischemic attack\b"),
    re.compile(r"\bischemic stroke\b"),
    re.compile(r"\bhemorrhagic stroke\b"),
]
STROKE_NEURO_FOCUS_TERMS = [
    "aphasia", "hemiparesis", "motor recovery", "cognitive impairment", "rehabilitation",
    "epilepsy", "seizure", "dementia", "parkinson", "multiple sclerosis", "ms ", "spasticity",
    "upper motor neuron", "neuromodulation", "neurostimulation", "spinal cord stimulation", "scs",
]

AUDIT_NEURO_ANCHORS = [
    "parkinson",
    "alzheimer",
    "multiple sclerosis",
    "ms ",
    "epilepsy",
    "seizure",
    "migraine",
    "fibromyalgia",
    "crps",
    "complex regional pain syndrome",
]

AUDIT_CARDIO_ANCHORS = [
    "arrhythmia",
    "atrial fibrillation",
    "coronary",
    "heart failure",
    "myocardial",
    "angioplasty",
    "ablation", 
    "sternotomy",
    "open heart",
    "cardiac surgery",
    "cardiothoracic"
]

AUDIT_IMMUNO_ANCHORS = [
    "lupus",
    "sle",
    "rheumatoid",
    "psoriasis",
    "crohn",
    "ulcerative colitis",
    "asthma",
]

AUDIT_MSK_ANCHORS = [
    "osteoarthritis",
    "arthroplasty",
    "knee osteoarthritis",
    "hip osteoarthritis",
]

AUDIT_METABOLIC_ANCHORS = [
    "diabetes",
    "diabetic",
]

AUDIT_RARE_ANCHORS = [
    "genetic",
    "inherited",
    "mutation",
    "orphan",
]

AUDIT_INFECTIOUS_ANCHORS = [
    "infection",
    "infectious",
    "hiv",
    "covid",
    "tuberculosis",
]
