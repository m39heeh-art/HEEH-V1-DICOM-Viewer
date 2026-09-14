# تقرير مشروع HEEH-V1(TM) DICOM Viewer

## نظرة عامة

**HEEH-V1(TM) DICOM Viewer** هو مشروع بحثي/تعليمي للتصوير الطبي (المقطعي CT وأشعة الرنين المغناطيسي MRI) مبني على **Streamlit** بواجهة تفاعلية مثل تطبيق مكتبي. يحذّر التطبيق بوضوح أنه **أداة بحث/تعليم وليست للاستخدام السريري** — تؤكد الواجهة هذا الحد بوضوح.

## القائمة الكاملة للميزات

- **19 فئة** في `app.py` (2,244 سطر): `BioScale`, `TissueClassifier`, `EdgeDetector`, `RadiomicsExtractor`, `XAIExplainer`, `VolumeVisualizer`, `ImageQualityMetrics`, `LongitudinalAnalyzer`, `PerfusionAnalyzer`, `ONNXInferenceEngine`, `SovereignOrchestrator`, `SovereignProcessor`, `SystemConfig`, `BaseAnalysis`, `QuantitativeEngine1`, `StructuralEngine1`, `MedicalAIVisionEngine`, `ClinicalApp`.
- **Sovereign L1–L6 pipeline**: معالجة متعددة المستويات (L1 الميزات البنيوية → L6 التحليل البُعدي/الكمّي)، مع مستويات متسلسلة.
- **XAI Attention Map (ViT)**: خريطة انتباه المحول البصري عبر `enable_attention` (السطور 2210–2224).
- **تقسيم المناطق (Region Segmentation)**: عبر `_heuristic_segment` (السطور 2226–2234) — تقسيم إرشادي (Heuristic) قائم على الكثافات وليس نموذجًا مدربًا — يعمل عندما `enable_monai` ولدى `roi_hu.size >= 4096`، مع إعادة إسقاط المنطقة عبر `coord_scale` بنصف قطر `radius = 64`.
- **فحص سلامة وحدات HU**: نطاق `[-1024, 3071]`.
- **مقياس التعرّف `"**Fingerprint:**"`**: أداة مرجعية لتمييز مخرجات الكشف داخل `tests/test_suite.py`.
- **واجهة المستخدم**: "Advanced Medical AI Tools" (1707–1713)، "🚀 Sovereign Matrix Launch" و"🔥 ALL GO - RUN EVERYTHING" (1715–1717)، "🏔️ Sovereign Analysis Forest" (1767)، "🧪 Test SovereignProcessor.process_node" (1770–1776)، **8 خدمات تعرض "✅ Online"** (1779–1793)، تفعيل تدفق TCIA إلى `~/.neuroproject_tcia` (1686–1693)، طبقة تأكيد قبل التشغيل (1695–1698)، تقسيم العظم/العضل/الدهون (1898–1918)، إحصاءات Radiomics (1946–1949)، وتمثيل ثلاثي الأبعاد 3D (1951–1967).
- **البنية**: وحدات داخل `core/` (`physiological_validator.py`, `constants.py`) و`engines/` (`analysis_orchestrator.py`, `monai_preprocessor.py`, `sitk_registration.py`, `clinical_metrics.py`)، إطلاق عبر `app.bat` / `launch.ps1` / `launch.sh`.
- **منطق كسري**: متوافق مع `engine::enable_attention` و`enable_monai`، بحيث التطبيق يعمل على عدة إصدارات.

## أحدث الملفات

- `app.py` — 9/1/2026 الساعة 5:11 م (## الملف المُحدَّث الرئيسي)
- `requirements.txt` و`pyproject.toml` — 9/1/2026 الساعة 4:34 م

## تناقضات أدوات الإقلاع والمتطلبات

- **Python Version Gate**: `app.bat` يتطلب 3.10+، `launch.ps1` يتطلب 3.11+، `launch.sh` يتطلب 3.14+، بينما `pyproject.toml` يشترط ≥3.11 — تناقض بين أدوات الإقلاع الثلاث.
- **ازدواجية التبعية**: `torchvision` مكرر في `requirements.txt`.
- **تبعية ناقصة**: `requests` موجود في `requirements.txt` لكنه غائب عن `pyproject.toml`.
- **بوابة الاختبار قديمة** في `launch.sh`: "17 passed, 2 warnings" مقارنة بـ **39 دالة اختبار** في `tests/test_suite.py` (505 سطر).
- `.venv` موجود لكن لا توجد `python.exe` في `.venv\Scripts\` → **لا يمكن تشغيل pytest حاليًا**.

## الملفات القديمة/الطرفية (8/19/2026)

- `zte_login.py` (3,032 بايت)
- `zte_menu.py` (3,203 بايت)
- `router_config*.py`

هذه أدوات شبكات زد تي إي (ZTE) لا علاقة لها بالتصوير الطبي — بقايا من مشروع آخر. **قرار الإزالة: موافقة المستخدم. التحقق أظهر أن ملفات `zte_*.py` و `router_config*.py` غير موجودة أصلًا (لا شيء للحذف)، وتم حذف باقي ملفات `zte_*.js` (zte_brute.js, zte_brute2.js, zte_label.js, zte_label2.js) بموافقة المستخدم.**

## التوصيات المُطبَّقة (Recs #1–#4)

- **استيراد التحقق (app.py:43)**: `from core.physiological_validator import PhysiologicalValidator as _PhysiologicalValidator` مع ربط `_validate_physiological_norms = _PhysiologicalValidator.validate_physiological_norms` — إزالة التعريف المكرر وضمان مصدر واحد.
- **تحقق النطاق (core/physiological_validator.py:66–112)**: `validate_physiological_norms(data, modality="ct")`؛ خرق النطاق → `st.error("**Range check failed:** ...")` ثم `ValueError("Input data outside the physiological range.")`؛ NaN/Inf → `st.error("NON_FINITE: Non-numeric values (NaN/Inf) detected in input.")` ثم `ValueError("Non-finite values detected in input sequence.")`؛ الوحدة `"HU" if resolved == "ct" else "IU"`؛ `return True` في النهاية.
- **استدعاء التحقق (app.py:1294–1300)**: `_validate_physiological_norms(data, "ct")`؛ `ValueError` يحوي `"Null values"` → `return (f"LOAD_ERROR: {str(e)}", path, "Volume (NIfTI / NRRD / MHA)")`؛ أخطاء أخرى → `st.session_state["validation_warning"] = str(e)` والمتابعة.
- **حارس الأنسجة (app.py:2098، 2111)**: `non_ct = (("DICOM" in mod_key) and ("CT" not in mod_key)) or ("NIFTI" in mod_key or "NRRD" in mod_key or "MHA" in mod_key)`؛ يعمل تقسيم العظم/العضل/الدهون فقط عندما `enable_tissue` وليس `non_ct`.

## تشخيص PyPI (PyPIDiagnostic)

- **تطابق التبعيات**: `requirements.txt` (21 سطرًا) و`pyproject.toml` (47 سطرًا) متطابقان في القائمة المشتركة؛ **torchvision** الآن مذكور مرة واحدة في كل ملف (غير مكرر)، و`requests` موجود في كليهما (`pyproject.toml:29`).
- **الفرق الوحيد**: قيد `zarr` — `requirements.txt:21` يشترط `>=3.1,<3.2` بينما `pyproject.toml:38` يشترط `>=3.3`.
- **الإصدارات المثبتة (تحقّق مباشر)**: `torch 2.13.0`, `torchvision 0.28.0`, `monai 1.6.0`, `simpleitk 2.5.5`, `requests 2.34.2`, `zarr 3.3.0`, `streamlit 1.59.1`, `pydicom 3.0.2`, `numpy 2.5.1`, `onnxruntime 1.27.0`. المثبَّت `zarr 3.3.0` يلبي `pyproject.toml` لكنه يخالف قيد `requirements.txt`.
- **توافق بايثون**: يعمل النظام على **Python 3.14.7** خارج النطاق المعلن `requires-python = ">=3.11,<3.14"` (`pyproject.toml:6`).
- **ملاحظة أمان (WDAC)**: سياسة Windows Defender تحظر تحميل `torch\lib\torch_global_deps.dll` وقت التشغيل (`OSError: [WinError 4551]`) — لا تؤثر على الاختبارات.
- **تصحيح بوابة الاختبار سطر 29–30**: المجموعة الآن **39 اختبارًا ناجحًا** (عبر بايثون النظام، 7.10ث، 8 تحذيرات إهمال فقط) — وبذلك أصبحت "17 passed" قديمة ويمكن تشغيل pytest عبر `python -m pytest tests\test_suite.py`.

## التحقق الشامل لسلسلة التصوير الطبي

### المنهجية

- قراءة كاملة لـ `app.py` (2484 سطرًا) دون فجوات، مع دليل `core/` بالكامل و`engines/` (المعالِج الأحادي، التسجيل، المقاييس السريرية) و`tests/test_suite.py` (505 سطرًا، 39 دالة اختبار).
- إعادة إطلاق موثَّقة: **39 اختبارًا ناجحًا، 8 تحذيرات إهمال فقط، خلال 7.09 ثانية**. جميع التحذيرات إهمال مكتبات فقط (torch.jit، pydicom، SimpleITK/NumPy 2.5).

### مراحل الحساب

- التدفق يبدأ عند `process_dicom` (`app.py:1152`) ويؤول إلى مسار قيم HU الخاص بـ CT.
- حراس السلامة: NaN/Inf → إيقاف حتمي `SOVEREIGN_HALT` (1183، 1201)؛ وسيط خارج النطاق المنطقي → `INTEGRITY_HALT` (1196)؛ استثناء غير متوقع → `CRITICAL_BALANCE_FAILURE` (1208).
- ضبط التصوير: `DISPLAY_PRESETS` (2242)؛ استرجاع المركز/العرض من وسمي `WindowCenter` / `WindowWidth` عند توفرهما (2249–2250)؛ معامل `lut_factor` (2264) والتمدد الطبقي إلى `[0,1]` (2268).
- الثوابت المعتمدة: `HU_MIN=-1024`، `HU_MAX=3071`، `PROBABILITY_THRESHOLD=0.80`، `DEFAULT_TARGET_SIZE=(128,128,128)`، `DEFAULT_MONAI_SPACING=(1,1,1)`.

### مدخلات الصور وقراءة الحجم

- الامتدادات المعتمدة: (.dcm، .dicom، .nii، .nii.gz، .nrrd، .mha، .mhd، .ima، .img) مع فحص سحر DICOM (قراءة 4 بايت من الإزاحة 128 == `DICM`)؛ `OSError` → يُرفض الملف (`_is_image_file` 1314–1329).
- قراءة الحجم: `_load_volume_file_cached` (882–895) عبر `nib.load` مع تطبيق `scl_slope`/`scl_inter` والتحويل إلى `float32`، مع SimpleITK كمسار احتياطي.
- **توضيح نزاهة**: التوثيق يعد "مفتاحًا على المسار + mtime"، لكن موقع الاستدعاء (1288) يمرر `(load_path, mtime)` ولا يستخدم `mtime` فعليًا، والقراءة بحد ذاتها غير مخزّنة.

### انتقالات المراحل وأنساق الواجهة

- لا تستخدم الواجهة `st.tabs`/`st.steps`/`st.selectbox`/`st.radio`؛ الانتقال عبر الأزرار مع `st.progress` (1499، 1733، 1876) ورسالة الجاهزية `st.info` عند 1937 في ذيل التوجيه (1919–1955)، وذيل التنزيل المباشر (1901–1918).
- نص الواجهة مختلط اللغة: شريط التقدم بالعربية، رسالة النجاح بالإنجليزية (1925–1926)، رسائل الخطأ/المعلومات بالعربية (1928–1932، 1937) — عِلمًا بأن الاختبار يستدعي guard مقابل `None` عند `tests/test_suite.py:415`.

### تحليل بيانات TCIA والمظاهر

- واجهات NBIA v4 الإنتاجية: `_TCIA_IMAGE_URL` = `https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getImage` و`_TCIA_META_URL` = `.../v4/getSeries`. يستخدم تنزيل الصور `SeriesInstanceUID` فقط، لأن v4 لا يقبل معامل `includeAnnotation` القديم الذي كان يسبب HTTP 400. توجد مسارات توافق v2 للبيانات القديمة، مع User-Agent ثابت "Mozilla/5.0 (Windows NT 10.0; Win64; x64)".
- المظاهر: ملفات `.tcia` فقط تُنزَّل عبر واجهة NBIA (`_download_tcia_series` 1493–1586) ضمن تدفق TCIA (1588)؛ وأنواع (.tsv/.csv/.txt) تمر بعرض مسبق دون تنزيل (التحليل 1330–1442، المعاينة 1444–1468).

### نتائج التحقق

- اكتمال التحقق الحالي دون كسر — 321 اختبارًا ناجحًا، بما في ذلك اختبار عقد NBIA v4 والتنزيل الحقيقي لسلسلة عامة من TCIA (51 ملف DICOM مع completion marker).
- تصحيح مرجعي: قسم الميزات القديم يشير إلى `_heuristic_segment` عند 2226–2234 (أرقام قديمة)؛ التحقق الجديد يُثبت أن نافذة التصوير عند 2242–2277 وتعريف `_heuristic_segment` عند 2280 (الجسم 2280–2293).

### حالة AV1/AVIF

- **أُلغي (تمت الإزالة الكاملة)**: أُزيل توجيه AV1/AVIF بالكامل من مسار الرفع المباشر داخل `_render_slice_viewer` بناءً على قرار التراجع عن استخدام تقنية AV1/AVIF. لم تعد توجد أي مراجع AV1/AVIF في `app.py` — جميع الملفات، بما فيها `.avif/.webm/.mkv/.av1`، تمر الآن عبر محمّل التصوير الطبي القياسي (NIfTI/DICOM/NRRD...) كما في السلوك الأساسي الأصلي.
- لم تُضف `.avif`/`.webm`/`.mkv`/`.av1` إلى `_IMAGE_EXTENSIONS` ولا `_is_image_file` — لا يجوز وصولها أبدًا إلى محمّل NIfTI/DICOM الطبي.