"""English scientific and medical UI terminology for the HEEH-V1™ DICOM Viewer.

All active user-facing labels are centralized here and use research-safe
medical-imaging terminology.
"""

# The active application uses English-only scientific terminology.
LANGUAGES = {"en": "English"}

# ---- Sidebar ----
SIDEBAR_TITLE = {
    "en": "Medical Image Input",
    "ar": "المدخلات السريرية",
}
SOURCE_MODE = {
    "en": "Image Source",
    "ar": "وضع المصدر",
}
DATA_PATH_LABEL = {
    "en": "Study or Series Directory",
    "ar": "مسار البيانات",
}
DATA_PATH_PLACEHOLDER = {
    "en": "C:/Medical/Data",
    "ar": "C:/Medical/Data",
}
UPLOAD_LABEL = {
    "en": "Upload Images",
    "ar": "رفع الصور",
}
AI_DOMAIN_LABEL = {
    "en": "Demonstration AI Domain (research only)",
    "ar": "نطاق رؤية الذكاء الاصطناعي (تجريبي فقط)",
}
WINDOW_PRESET_LABEL = {
    "en": "Display Window Preset",
    "ar": "النمط الافتراضي للنافذة",
}

# ---- Analysis sections ----
SECTION_INPUT = {
    "en": "Input",
    "ar": "المدخلات",
}
SECTION_AI_TOOLS = {
    "en": "AI & Advanced Tools",
    "ar": "أدوات الذكاء الاصطناعي والمتقدمة",
}
SECTION_ANALYSIS = {
    "en": "Image Analysis",
    "ar": "نطاق التحليل",
}
SECTION_SETTINGS = {
    "en": "Display Settings",
    "ar": "إعدادات العرض",
}

# ---- Feature labels ----
FEATURE_MONAI = {
    "en": "MONAI Preprocessing",
    "ar": "المعالجة المسبقة MONAI",
}
FEATURE_SITK = {
    "en": "SimpleITK Registration",
    "ar": "تسجيل SimpleITK",
}
FEATURE_TISSUE = {
    "en": "Research Tissue-Composition Map",
    "ar": "تصنيف الأنسجة",
}
FEATURE_EDGES = {
    "en": "Edge Detection",
    "ar": "كشف الحواف",
}
FEATURE_QUALITY = {
    "en": "Image Quality Proxies (SNR/CNR)",
    "ar": "جودة الصورة",
}
FEATURE_RADIOMICS = {
    "en": "Radiomics-Style Quantitative Features (research)",
    "ar": "سمات الإشعاعيات",
}
FEATURE_XAI = {
    "en": "Model Attention Map (XAI)",
    "ar": "خريطة انتباه XAI",
}
FEATURE_TMAP = {
    "en": "Bone/Muscle/Fat Map",
    "ar": "خريطة العظام/العضلات/الدهون",
}
FEATURE_VIZ = {
    "en": "Volumetric Visualization (MIP/MPR/3D)",
    "ar": "تصور ثلاثي الأبعاد",
}

# ---- Buttons ----
BTN_RUN_ANALYSIS = {
    "en": "Run Full Analysis",
    "ar": "تشغيل التحليل الكامل",
}
BTN_TEST_ENGINE = {
    "en": "Test Engine",
    "ar": "اختبار المحرك",
}

# ---- Status messages ----
MSG_READY = {
    "en": "Ready. Select a study, series, or image file to begin.",
    "ar": "النظام جاهز. ارفع أو حدد مسار البيانات للبدء.",
}
MSG_NO_FILES = {
    "en": "No valid image files found.",
    "ar": "لم يتم العثور على ملفات صور صالحة.",
}
MSG_LOADING = {
    "en": "Loading medical image...",
    "ar": "جارٍ تحميل الصورة الطبية...",
}
MSG_ANALYZING = {
    "en": "Analyzing...",
    "ar": "جارٍ التحليل...",
}

# ---- Disclaimer ----
DISCLAIMER_TITLE = {
    "en": "Not a medical device",
    "ar": "ليس جهازاً طبياً",
}
DISCLAIMER_TEXT = {
    "en": (
        "This application is for research and education only. "
        "It must NOT be used for diagnosis, prognosis, or any clinical decision. "
        "All tissue/organ labels describe image appearance, not medical findings. "
        "Consult a qualified radiologist for interpretation."
    ),
    "ar": (
        "هذه الأداة مخصصة للبحث والتعليم فقط. "
        "يُحظر استخدامها للتشخيص أو التنبؤ أو أي قرار سريري. "
        "جميع تسميات الأنسجة/الأعضاء تصف مظهر الصورة وليس النتائج الطبية. "
        "استشر أخصائي أشعة مؤهلاً للتأويل."
    ),
}

# ---- Error messages ----
ERR_ENGINE_INIT = {
    "en": "Failed to initialize analysis engine",
    "ar": "فشل في تهيئة محرك التحليل",
}
ERR_LOAD_FAILED = {
    "en": "Could not load the medical image",
    "ar": "تعذر تحميل الصورة الطبية",
}
ERR_DATA_REJECTED = {
    "en": "Data rejected: invalid pixel values detected",
    "ar": "تم رفض البيانات: تم اكتشاف قيم بكسل غير صالحة",
}
ERR_OUT_OF_RANGE = {
    "en": "Data outside valid range",
    "ar": "البيانات خارج النطاق الصالح",
}
ERR_INVALID_DIR = {
    "en": "Invalid directory path. Enter a valid folder or file path.",
    "ar": "مسار مجلد غير صالح. أدخل مسار مجلد أو ملف صالح.",
}
ERR_INVALID_COORDS = {
    "en": "Invalid coordinates received from image interaction.",
    "ar": "إحداثيات غير صالحة وردت من التفاعل مع الصورة.",
}
ERR_ANALYSIS_FAILED = {
    "en": "Analysis failed. Please check the selected region and try again.",
    "ar": "فشل التحليل. يرجى التحقق من المنطقة المحددة والمحاولة مرة أخرى.",
}
CAP_EDGE_DETECTION = {
    "en": "Edge Detection",
    "ar": "كشف الحواف",
}
CAP_3D_VISUALIZATION = {
    "en": "3D Visualization",
    "ar": "عرض ثلاثي الأبعاد",
}
ERR_NO_VALID_FILES = {
    "en": "No valid data files found.",
    "ar": "لم يتم العثور على ملفات بيانات صالحة.",
}

# ---- Acquisition / integrity errors ----
ERR_ACQUISITION = {
    "en": "Acquisition Error",
    "ar": "خطأ في اقتناء الصورة",
}
ERR_EMPTY_VOXEL_DATA = {
    "en": "Image contains no valid voxel data (empty array).",
    "ar": "الصورة لا تحتوي على بيانات فوكسل صالحة (مصفوفة فارغة).",
}
ERR_ROI_OUT_OF_RANGE = {
    "en": "ROI out of range: median HU outside the valid CT range [-1024, 3071].",
    "ar": "منطقة الاهتمام خارج النطاق: متوسط وحدات HU خارج نطاق التصوير المقطعي الصالح [-1024، 3071].",
}
ERR_STRUCTURAL_INSTABILITY = {
    "en": "Structural Instability: the L6 map failed the stability/balance check.",
    "ar": "عدم استقرار بنيوي: فشلت خريطة L6 في فحص التوازن.",
}

# ---- Confidence / fallback status ----
LOW_CONFIDENCE_MANUAL_REVIEW = {
    "en": "LOW CONFIDENCE - MANUAL REVIEW REQUIRED",
    "ar": "ثقة منخفضة - يلزم مراجعة يدوية",
}
CAP_FALLBACK_MODE = {
    "en": "Fallback mode - heuristic interpretation",
    "ar": "وضع احتياطي - تأويل استدلالي",
}

# ---- Viewer / analysis captions ----
CAP_3D_VISUALIZATION = {
    "en": "3D Visualization",
    "ar": "تصور ثلاثي الأبعاد",
}
CAP_ATTENTION_OVERLAY = {
    "en": "Attention Overlay (ViT)",
    "ar": "طبقة الانتباه فوق الصورة (ViT)",
}
CAP_BONE_MUSCLE_FAT = {
    "en": "Bone / Muscle / Fat",
    "ar": "عظام / عضلات / دهون",
}
CAP_IMAGE_QUALITY_METRICS = {
    "en": "Image Quality Metrics",
    "ar": "مقاييس جودة الصورة",
}
CAP_MIP = {
    "en": "MIP (Axis 0)",
    "ar": "MIP (المحور 0)",
}
CAP_MPR = {
    "en": "MPR Mid-Slice",
    "ar": "MPR (شريحة وسطية)",
}
CAP_SEGMENTATION_MASK = {
    "en": "Segmentation Mask",
    "ar": "قناع التقسيم",
}
CAP_STRUCTURAL_CONNECTOME = {
    "en": "Structural Connectome",
    "ar": "الترابط البنيوي",
}
CAP_TARGET_ROI = {
    "en": "Target ROI (Pure-Gray)",
    "ar": "منطقة الاهتمام المستهدفة (رمادي نقي)",
}
CAP_TISSUE_COMPOSITION = {
    "en": "Tissue Composition",
    "ar": "تكوين الأنسجة",
}
CAP_VIEWER = {
    "en": "Medical image viewer",
    "ar": "عارض الصور الطبية",
}

# ---- DICOM Structured Report viewer ----
SR_REPORT_TITLE = {
    "en": "DICOM Structured Report",
    "ar": "تقرير DICOM المنظم",
}
SR_REPORT_HINT = {
    "en": "Review measurements imported from a DICOM Structured Report.",
    "ar": "راجع القياسات المستوردة من تقرير DICOM منظم.",
}
SR_PARSE_FAILED = {
    "en": "Unable to parse the DICOM Structured Report",
    "ar": "تعذر تحليل تقرير DICOM المنظم",
}
SR_HEADER_DETAILS = {
    "en": "Report details",
    "ar": "تفاصيل التقرير",
}
SR_REFERENCED_IMAGES = {
    "en": "Referenced images",
    "ar": "الصور المشار إليها",
}
SR_MEASUREMENTS_TABLE = {
    "en": "Measurements",
    "ar": "القياسات",
}
SR_IMPORT_BUTTON = {
    "en": "Import measurements",
    "ar": "استيراد القياسات",
}
SR_IMPORT_NOTICE = {
    "en": "Imported {n} measurement(s).",
    "ar": "تم استيراد {n} من القياسات.",
}
SR_IMPORT_SKIPPED_RADIUS = {
    "en": "Some radius measurements were skipped because their source image was unavailable.",
    "ar": "تم تخطي بعض قياسات نصف القطر لعدم توفر الصورة المصدر.",
}
SR_NO_MEASUREMENTS = {
    "en": "No supported measurements were found in this report.",
    "ar": "لم يتم العثور على قياسات مدعومة في هذا التقرير.",
}

# ---- Deep analysis section labels ----
SECTION_QUANTITATIVE_DENSITY = {
    "en": "L4: Quantitative Density",
    "ar": "L4: الكثافة الكمية",
}
SECTION_CT_QUANTITATIVE_METRICS = {
    "en": "CT Quantitative Metrics (IEC / ACR / AAPM)",
    "ar": "المقاييس الكمية للتصوير المقطعي (IEC / ACR / AAPM)",
}
LABEL_INFERENCE_DIMENSION = {
    "en": "[INFERENCE DIMENSION]",
    "ar": "[بُعد الاستدلال]",
}
LABEL_DOMINANT_TISSUE = {
    "en": "Dominant tissue",
    "ar": "النسيج السائد",
}

# ---- CT quantitative metric labels ----
LABEL_MEAN_HU = {
    "en": "Mean CT Number (HU)",
    "ar": "متوسط HU",
}
LABEL_SAMPLE_SIZE = {
    "en": "ROI Voxel Count (n)",
    "ar": "حجم عينة منطقة الاهتمام",
}
LABEL_STD_NOISE = {
    "en": "Intensity Variability / Noise Proxy (SD)",
    "ar": "الانحراف المعياري (الضجيج)",
}
LABEL_SNR = {
    "en": "Water-Referenced SNR Proxy",
    "ar": "التباين/الضجيج نسبةً إلى الماء",
}
LABEL_CNR = {
    "en": "Tissue-Class CNR Proxy",
    "ar": "CNR",
}
LABEL_LOW_CONTRAST_CNR = {
    "en": "Low-contrast CNR proxy",
    "ar": "مؤشر CNR للتباين المنخفض",
}

# The active UI is English-only; this remains as a compatibility constant for
# older imports that queried text direction.
RTL_LANGS = set()
