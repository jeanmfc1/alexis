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
TA_PSYCHIATRY = "Psychiatry"
TA_GI = "Gastrointestinal / Hepatic"
TA_RESPIRATORY = "Respiratory"
TA_OPHTHALMOLOGY = "Ophthalmology"
TA_UROLOGY = "Urology"
TA_NON_DISEASE = "Non-disease drug study"
TA_UNASSIGNED = "Unassigned drug study"
TA_DENTAL = "Dental / Oral Health"
TA_DERMATOLOGY = "Dermatology"
TA_HEMATOLOGY = "Hematology"
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
    # Common abbreviations not caught by above
    "nsclc", "sclc", "hcc", "crc", "rcc", "urothelial carcinoma",
    "pdac", "pancreatic ductal adenocarcinoma",
    "tnbc", "triple negative breast",
    "aml", "cml", "cll", "mds", "myelodysplastic",
    "dlbcl", "follicular lymphoma", "hodgkin", "non-hodgkin",
    # Cluster 3 additions
    "hemangioendothelioma", "kaposiform",
    "squamous intraepithelial lesion", "hsil", "lsil",
    # Neuropathy / mesothelioma — safer here than in Neuro/Respiratory
    "mesothelioma", "chemotherapy-induced",
]

PSYCHIATRY_KW = [
    "cocaine use disorder",
    "smoking cessation",
    "substance use disorder",
    "addiction",
    # Suicidality
    "suicidal ideation", "suicidality", "suicide attempt", "self-harm",
    # Cannabis / opioid / psychedelic — only specific disorder terms, not drug names
    "cannabis use disorder", "opioid use disorder",
    "alcohol use disorder", "alcohol dependence",
    # Eating / anxiety / other
    "anorexia nervosa", "bulimia", "binge eating",
    "obsessive-compulsive", "ocd", "ptsd", "post-traumatic stress",
    "borderline personality", "attention deficit",
    # Title-signal additions
    "psychosis", "psychotic", "vaping cessation",
    "nicotine pouch", "nicotine use",
    "thc", "methamphetamine", "amphetamine", "benzodiazepine",
]

INFECTIOUS_KW = [
    "infectious", "infection", "viral", "virus", "bacterial", "bacteria",
    "fungal", "fungus", "hiv", "covid", "sars-cov-2", "influenza", "flu",
    "hepatitis", "tuberculosis", "tuberculous", "malaria", "antiviral",
    "antimicrobial", "antibiotic", "sepsis", "pneumonia", "vaccine", "vaccination",
    # Title-signal additions
    "herpes zoster", "zoster", "herpes simplex",
    "hpv", "hbv", "hcv", "rsv", "dengue",
    "clostridium", "clostridioides", "candida", "aspergillus",
]
IMMUNO_KW = [
    "autoimmune", "inflammation", "inflammatory", "immune", "immuno",
    "lupus", "sle", "rheumatoid", "arthritis", "psoriasis",
    "eczema", "atopic dermatitis", "atopic hand", "atopic foot", "atopic eczema", "crohn", "crohn's", "ulcerative colitis",
    "ibd", "asthma", "multiple sclerosis", "ms ", "myasthenia gravis", "ocular myasthenia gravis", "gmg",
    # Allergy / anaphylaxis
    "allerg", "anaphylaxis", "anaphylactic",
    "food allergy", "drug allergy", "cow milk",
]
NEURO_KW = [
    "neurology", "neurologic", "neurological", "cns", "brain", "spinal",
    "alzheimer", "parkinson", "dementia", "neurodegenerative", "epilepsy", "seizure",
    "migraine", "depression", "schizophrenia", "bipolar", "psychiatric", "autism", "adhd",
    "aphasia", "hemiparesis", "motor recovery", "cognitive impairment", "rehabilitation", "palliative care", "palliative sedation", "end of life care",
    "psychological distress palliative",
    # Title-signal additions
    "acoustic reflex", "tinnitus", "vestibular", "cochlear",
    "peripheral neuropathy", "neuropathic",
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
    "cabg", "endarterectomy", "carotid", "pulmonary embolism",
    "vasospasm", "pulmonary hypertension", "pulmonary artery hypertension",
    "ptca", "balloon catheter", "drug-coated balloon", "dcb",
    "aneurysm", "preeclampsia", "postpartum hypertension", "pregnancy-induced hypertension",
]
METABOLIC_KW = [
    "metabolic", "endocrine", "diabetes", "diabetic", "obesity", "insulin",
    "lipid", "cholesterol", "dyslipidemia", "thyroid", "hyperthyroid",
    "hypothyroid", "metabolic syndrome", "fatty liver", "nafld", "nash",
    # Rare lipid disorders
    "familial chylomicronemia", "fcs", "hypertriglyceridemia",
    "familial hypercholesterolemia", "lipoprotein lipase deficiency",
    # Other metabolic
    "hyperuricemia", "gout", "phenylketonuria", "pku",
    "gaucher", "fabry", "pompe",
]
RARE_KW = [
    "rare disease", "orphan", "genetic", "inherited", "deficiency",
    "lysosomal", "dystrophy", "fragile x", "cystic fibrosis", "spinal muscular atrophy", "sjögren syndrome",
    "interferonopathy", "proteinuric kidney disease",
    # Specific rare syndromes seen in unassigned trials
    "phelan-mcdermid", "phelan mcdermid",
    "pitt hopkins", "pitt-hopkins",
    "angelman syndrome", "angelman",
    "prader-willi", "prader willi",
    "rett syndrome", "rett's syndrome",
    "kabuki syndrome",
    "dravet syndrome",
    "batten disease",
    "hunter syndrome", "hurler syndrome",
    "niemann-pick", "niemann pick",
    "sanfilippo",
    "mucopolysaccharidosis", "mps ",
    "transthyretin", "ttr amyloid",
    # Cluster 3 additions
    "primary hyperoxaluria", "hyperoxaluria",
    "hypochondroplasia",
    "primary cutaneous amyloidosis",
    "cutaneous amyloidosis",
    # Title-signal additions
    "erythropoietic protoporphyria", "porphyria",
    "x-linked protoporphyria",
    # Cluster 4 additions
    "spastic paraplegia", "hereditary spastic paraplegia", "hsp",
    "mecp2",
    "congenital central hypoventilation syndrome", "cchs", "ondine syndrome",
    "gne myopathy",
    "rvcl", "retinal vasculopathy cerebral leukoencephalopathy",
    "congenital melanocytic nevus",
    "runx1 familial platelet disorder",
    "spastic paraplegia type",
]
MSK_KW = [
    "osteoarthritis", "musculoskeletal", "low back pain", "back pain",
    "myofascial pain", "hip osteoarthritis", "knee osteoarthritis",
    "arthroplasty", "hip arthroplasty", "knee arthroplasty", "total knee arthroplasty", "total hip arthroplasty", "subacromial",
    "patellofemoral", "patello femoral", "anterior knee pain", "popliteus", "abdominoplasty", "bunionectomy", "rib fracture",
    "hernia repair", "hernia surgery",
    # Fractures seen in unassigned trials
    "hip fracture", "hip fractures", "femoral fracture", "femur fracture",
    "wrist fracture", "distal radius fracture",
    "vertebral fracture", "compression fracture",
    "tibial fracture", "ankle fracture",
    # Ligament / tendon injuries
    "anterior cruciate ligament", "acl injury", "acl reconstruction",
    "rotator cuff", "rotator cuff tear", "rotator cuff repair",
    "achilles tendon", "achilles tendinopathy",
    # Other MSK
    "scoliosis", "kyphosis", "spinal stenosis",
    "intervertebral disc", "disc herniation",
    "osteonecrosis", "avascular necrosis",
    "osteoporosis", "bone density",
    # Title-signal additions
    "spine surgery", "spinal surgery", "lumbosacral",
    "articular cartilage", "rhizarthrosis",
    "synovitis", "intra-articular",
    "meniscus", "meniscal",
    "tendinopathy", "tendinitis", "bursitis",
    "spondylosis", "spondylolisthesis", "facet joint",
    # Cluster 4 additions
    "sacroiliac joint", "sacroiliac",
    "compartment syndrome",
    "supracondylar", "humerus fracture",
    "trigger finger", "dupuytren", "carpal tunnel",
    "shoulder arthroplasty", "shoulder replacement",
    "periprosthetic", "prosthetic joint",
]
GI_KW = [
    "cirrhosis", "steatohepatitis", "hepatic", "cholestasis", "inflammatory bowel", "crohn", "ulcerative colitis",
    "gastrectomy", "pancreatic insufficiency", "pancreatic enzyme", "esophageal", "hemorrhoid", "hemorrhoids", "colorectal adenoma",
    "colorectal neoplasia","esophagogastric junction", "achalasia", "bloody diarrhea", "radiation esophagitis",
    # Title-signal additions (endoscopy/gastroscopy excluded — too many FPs on sedation trials)
    "hepatotoxicity", "drug-induced liver", "dili",
    "pancreatitis", "cholangitis", "biliary", "cholelithiasis",
    "bowel prep", "colonoscopy prep",
    # Nutrition / TPN
    "parenteral nutrition", "enteral nutrition", "tpn",
    "malnutrition", "nutritional deficiency",
    # Cluster 4 additions
    "irritable bowel syndrome", "ibs-c", "ibs-d", "ibs-m",
    "functional dyspepsia", "postprandial distress syndrome",
    "liver regeneration",
    "gastric intestinal metaplasia", "intestinal metaplasia",
    "chronic idiopathic constipation", "functional constipation",
    "gastroparesis",
    "fecal microbiota", "gut microbiome", "gut microbiota",
]
UROLOGY_KW = [
    "chronic kidney disease","ckd","glomerular","proteinuria","nephropathy","apol1",
    "urinary incontinence", "stress incontinence", "neurogenic bladder", "overactive bladder", "ureteral", "urological", "ovarian reserve",
    "diminished ovarian reserve", "fertility",
    # Gynecological / reproductive seen in unassigned trials
    "primary dysmenorrhea", "dysmenorrhea", "endometriosis",
    "ivf", "in vitro fertilization", "in vitro fertilisation",
    "polycystic ovary", "pcos",
    "uterine fibroid", "leiomyoma",
    "vulvodynia", "vaginismus",
    "benign prostatic hyperplasia", "bph", "lower urinary tract",
    "renal colic", "nephrolithiasis", "kidney stone",
    # Cluster 3 additions — contraception was missing
    "contraception", "contraceptive",
    # Title-signal additions
    "cystoplasty", "bladder augmentation",
    "vaginal aplasia", "vaginal construct",
    "hysterectomy", "myomectomy",
    "cystectomy", "prostatectomy",
    "nephrectomy", "ureteroscopy",
    # Pregnancy / obstetrics
    "pregnant", "pregnancy", "gestational", "obstetric",
    "postpartum", "maternal", "fetal", "foetal",
    "lactation", "breastfeed", "cesarean", "caesarean",
    "eclampsia", "preeclampsia", "labor induction", "labour induction",
    "neonatal", "neonat",
    # Sexual / reproductive health
    "erectile", "menopause", "menopausal",
    "dyspareunia", "vaginal atrophy", "genitourinary syndrome",
    # Cluster 4 additions
    "hemodialysis", "peritoneal dialysis", "end stage renal disease", "esrd",
    "ovarian stimulation", "oocyte retrieval", "follicle stimulation",
    "gnrh agonist trigger", "dual trigger",
    "renal amyloidosis", "al amyloidosis",
    "renal anemia", "anemia of chronic kidney",
    "iron deficiency dialysis", "iron isomaltoside",
]

OPHTHALMOLOGY_KW = [
    "macular degeneration","retinopathy","diabetic eye", "retinal detachment",
    "rhegmatogenous retinal", "macular telangiectasia", "vitreoretinal",
    # Cluster 3 additions
    "cataract", "age-related cataract", "age related cataract",
    "glaucoma", "intraocular pressure",
    # Title-signal additions
    "myopia", "myopic", "staphyloma",
    "keratoconus", "corneal",
    "conjunctivitis", "blepharitis", "eyelid",
    "vitreous", "macular hole",
    # Cluster 4 additions
    "retinitis pigmentosa", "x-linked retinitis pigmentosa",
    "stargardt", "stargardt disease",
    "optic neuritis", "optic neuropathy",
    "neuromyelitis optica", "nmosd",
]

DENTAL_KW = [
    "dental implant", "tooth", "teeth", "periodontal", "peri-implant", 
    "peri-implantitis", "periimplantitis", "oral health", "bruxism", 
    "pulpotomy", "extraction socket", "gingivitis", "periodontitis",
    "bleaching sensitivity", "tooth sensitivity", "dental sensitivity",
    "oral care", "endodontic", "root canal",
    # Title-signal additions
    "tmj", "temporomandibular",
    "aphthous", "oral ulcer", "aphthous ulcer",
    "interdental", "xerostomia", "dry mouth", "salivary",
    "malocclusion",
    # Cluster 4 additions
    "dental caries", "caries",
    "luting cement", "dental cement", "resin cement",
    "vital pulp therapy", "pulp capping",
    "dental anxiety",
    "tooth extraction", "alveolar",
    "fissure sealant", "pit and fissure",
]

DERMATOLOGY_KW = [
    "keloid", "scar tissue", "hypertrophic scar",
    "vitiligo", "alopecia", "hair loss",
    "acne", "rosacea", 
    "skin lesion", "skin disorder", "xerosis",
    "dry skin",
    "xerosis cutis",
    # Additional conditions seen in unassigned trials
    "prurigo nodularis", "prurigo",
    "hidradenitis suppurativa",
    "pemphigus", "pemphigoid", "epidermolysis bullosa",
    "ichthyosis", "psoriatic skin",
    "urticaria", "chronic urticaria", "chronic spontaneous urticaria",
]

HEMATOLOGY_KW = [
    "hematopoietic reconstitution", "bone marrow recovery",
    "granulocyte collection", "stem cell mobilization",
    "clonal cytopenia", "cytopenia", "neutropenia",
    "thrombocytopenia", "anemia non-malignant",
    "g-csf", "filgrastim", "plerixafor", "thalassemia", "alpha-thalassemia", "beta-thalassemia",
    "monoclonal gammopathy",
    "neuroblastoma",
    # Cluster 4 additions
    "hemophilia", "haemophilia",
    "hemophilia a", "hemophilia b",
    "platelet disorder", "familial platelet disorder",
    "platelet transfusion refractoriness",
    "runx1",
    "sickle cell disease", "sickle cell",
    "aplastic anemia", "aplastic anaemia",
    "paroxysmal nocturnal hemoglobinuria", "pnh",
    "immune thrombocytopenia", "itp",
    "von willebrand", "factor viii", "factor ix",
]

RESPIRATORY_KW = [
    "copd", "chronic obstructive pulmonary",
    "bronchitis", "emphysema",
    "pulmonary fibrosis", "interstitial lung disease",
    "fibrosing interstitial lung", "lung disease",
    "respiratory infection", "otitis media",
    # Cluster 3 additions
    "chronic rhinosinusitis", "rhinosinusitis", "sinusitis",
    "nasal polyp", "nasal polyps",
    # Title-signal additions
    "pleurodesis", "pleural effusion", "pleural empyema", "empyema",
    "pneumothorax", "air leak",
    "bronchiectasis", "sleep apnea", "obstructive sleep",
    # ENT
    "otitis", "rhinitis", "tonsil", "adenoid",
    "laryngeal", "pharyngeal", "larynx", "pharynx",
    "snoring", "nasal obstruction", "nasal congestion",
    # Cluster 4 additions
    "ards", "acute respiratory distress syndrome",
    "mycobacterium avium complex", "mac pulmonary", "mac lung",
    "chronic pulmonary aspergillosis",
    "lung microbiome", "respiratory microbiome",
    "neuromuscular blockade ventilation", "lung protective ventilation",
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

# policy/ta_policy.py

"""
Therapeutic Area policy

This module defines policy decisions applied AFTER therapeutic area
evidence has been detected.

These policies do not affect:
- ontology scope
- MeSH evidence detection
- fallback TA assignment

They control how TA information is presented and summarized.
"""

TA_PRIORITY_ORDER = [
    # Disease-centric programs dominate operational framing
    "Oncology",
    "Infectious Disease",
    "Rare / Genetic",

    # Mechanism-driven category (secondary to disease-centric framing)
    "Immunology / Inflammation",

    # CNS categories with distinct regulatory pathways
    "Neurology / CNS",
    "Psychiatry",

    # Organ-system categories
    "Cardiovascular",
    "Metabolic / Endocrine",
    "Gastrointestinal / Hepatic",
    "Respiratory",
    "Ophthalmology",
    "Urology",
    "Musculoskeletal",

    # NEW: Additional organ/specialty categories
    "Hematology",
    "Dermatology",
    "Dental / Oral Health",
]


def select_primary_ta(detected_tas: list[str]) -> str | None:
    """
    Select a single primary therapeutic area when multiple TAs are detected.

    Rules:
    - First TA in TA_PRIORITY_ORDER wins
    - If no priority match exists, fall back to alphabetical order
      to preserve deterministic behavior

    This is a presentation / analytics policy, not a biological claim.
    """
    for ta in TA_PRIORITY_ORDER:
        if ta in detected_tas:
            return ta

    return sorted(detected_tas)[0] if detected_tas else None
