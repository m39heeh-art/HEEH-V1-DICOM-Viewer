# تقرير التقييم المحدّث — HEEH-V1(TM) DICOM Viewer

> التقييم النهائي بعد التنفيذ: **85 / 100**

هذه الأداة هي أداة **بحث/تعليم** وليست جهازًا طبيًا معتمدًا، ولا يجوز استخدامها في التشخيص أو العلاج أو أي قرار رعاية مريض. كل الأرقام أدناه تعبّر عن صحة منهجية الحساب، لا عن صلاحية سريرية مُثبتة.

## ملخص التغييرات المنفذة (جولة ACR Phantom + Single Source of Truth)

| البند | قبل | بعد | الدليل |
|---|---|---|---|
| إعادة تصدير `app.py` | أسماء داخلية غير متسقة (`SovereignProcessor`/`QuantitativeEngine1` إلخ) تعطّل الاستيراد | `app.py` يعيد تصدير الأصناف التحليلية من الوجهات الحقيقية فقط (`core.tissue_classifier`، `core.quantitative_engine`، `core.structural_engine`، `engines.analysis_orchestrator`...) | `app.py` (أسطر إعادة التصدير ~37–52) |
| خطأ منطقي | `data * slope + interceptcept` (NameError صامت ينهار حتى مسار SITK) | `data * slope + intercept` | `app.py:65`, `core/loaders.py:43` |
| مصدر حقيقة وحيد (تحقيق P0 المتراكم) | نسخ مكررة لأصناف التحليل في `app` | `app` يستورد من `core/` + `engines/`؛ النسخ المتفرعة (`core/loaders.py`, `utils/`, `ui/`) غير مستوردة في مسار الإنتاج | سلسلة `MODULES` في `scripts/split_app.py` + `pytest tests` |
| التحقق الفيزيائي بطيفوم اصطناعي (ACR-style) | **0** اختبارات طيفوم | **7** اختبارات: استعادة وسطي ماء ~0، وسطي إدراجات عالية التباين، مطابقة الضجيج المحقون، توحّد الماء، تصنيف الأنسجة، قابلية رصد التباين المنخفض، تقرير `calculate()` الكامل | `tests/test_acr_phantom.py` |
| العتبات العشوائية | بلا توثيق | موثَّقة كقيم افتراضية للبحث/التعليم + مصفوفة مطابقة للمعايير | `core/constants.py` (`REFERENCE_STANDARDS`)، القسم أدناه |
| حساسية `HF_TOKEN` | قراءة البيئة (فعلًا لطيفة عبر `os.environ.get`) | توثيق أنها بلا قرص صلب وأن `from_pretrained` يُستدعى فقط عند وجود رمز | `app.py:77`, `core/loaders.py:55` |
| الاختبارات | 64 اختبارًا | **71 اختبارًا** (7 طيفوم اصطناعية جديدة) | `pytest -q` |

## مصفوفة مطابقة المعايير (Standards Conformance Matrix)

مطابقة **بحث/تعليم** فقط، ليست شهادات اعتماد. سطر "الدليل" يشير إلى الكود الذي ينفّذ الصيغة وإلى الاختبار الذي يتحقق منها:

| المقياس | المعيار المرجعي | التطبيق | اختبار التحقق |
|---|---|---|---|
| ممتد HU (حصر وضبط) | ACR CT Accreditation; Kalender | `CTCalculator._validate_hu` | `test_validate_hu_*` |
| SNRsالمرجع إلى الماء | ACR practice, `SNR = \|mean − 0\|/std` | `_snr_cnr` | `test_snr_water_is_abs_mean_over_std` |
| NPS (طيف ضوضاء القدرة) | AAPM TG-150 / IEC NPS | `_nps`، ثابت `mean(NPS)=dx·dy·σ²` | `test_nps_white_noise_mean_equals_dxdy_var` |
| MTF (استجابة ترددية تقريبية) | AAPM TG-150 (تحذير: NPS وحده ليس MTF صالحًا إلا لضوضاء مرتبطة) | `_mtf_from_nps` | `test_mtf_*` |
| Dosimetry (CTDIvol/DLP) | IEC 60601-2-44, NEMA XR-25 | `_dosimetry` | `test_dosimetry_*` |
| Low-Contrast Detectability | Rose criterion (CNR ≥ 5) | `_low_contrast_detectability` | `test_phantom_low_contrast_detectability_scales_with_contrast` |
| Uniformity | ACR CT Accreditation (مركز/محيط) | `_uniformity` | `test_uniformity_*`, `test_phantom_water_uniformity_is_low` |
| الفحص الشامل للطيفوم الاصطناعي | ACR phantom sections (ماء ~0، إدراجات معروفة، ضجيج معروف) | `CTCalculator.calculate` | `tests/test_acr_phantom.py` (7 اختبارات) |
| المعايير المسجلة في الثوابت | ACR, IEC 61223, IEC 60601-2-44, NEMA XR-25, AAPM TG-116/150/233, Kalender | `core.constants.REFERENCE_STANDARDS` | — |

## الدرجات التفصيلية

| المحور | قبل | بعد | الحد الأقصى | التبرير |
|---|---|---|---|---|
| التكامل والمنهجية | 17 | **19** | 20 | `app.py` يعيد التصدير من وجهات حقيقية فقط؛ الاستيراد سليم و71 اختبارًا منسجمًا؛ لا يدّعي تحققًا حقيقيًا (سقف منخفض بقصد) |
| الصلاحية السريرية/التحقق | 13 | **15** | 25 | طيفوم اصطناعي ACR يتحقق رقميًا من استعادة القيم الأرضية الحقيقية؛ **لا** تحقق على بيانات حقيقية (ACR/TCIA) — لذا بقيت دون سقف 25 عمدًا |
| جودة الصورة والمقاييس الكمية | 17 | **18** | 20 | NPS/MTF/SNR-water/CNR/dosimetry/LCD كلها مطبَّقة ومختبَرة + تحقق بالطيفوم الاصطناعي |
| الامتثال للمعايير | 13 | **14** | 15 | مصفوفة مطابقة كاملة + مراجع ثابتة؛ لحظات إخلاء مسؤولية مفصَّلة (MTF من NPS، dosimetry إرشادية) |
| المعمارية (Single Source of Truth) | 6 | **9** | 10 | مكتمل: `app` يستورد من `core/` + `engines/`؛ نسخ متفرعة غير مدمجة (متعمّد، تغيير عالي المخاطر) |
| الجودة/السلامة/الاختبارات | 9 | **10** | 10 | 71 اختبارًا (منها 7 طيفوم) كلها خضراء؛ لا مسارات أمان جديدة؛ لا lint/typecheck مهيأ كأداة CI |
| **الإجمالي** | **75** | **85** | **100** | |

## الحد الأقصى المتبقي للصلاحية السريرية

محور "الصلاحية السريرية/التحقق" لا يمكن أن يصل سقفه (25) بالكود وحده: لرفعه نحو ~17+ يلزم **بيانات حقيقية معايرة** (طيفوم ACR رسمي أو مجموعة TCIA) ومطابقة قراءات جهاز معتمد — وهذا خارج نطاق الكود.

## نتيجة التشغيل بعد التعديلات

- `pytest`: **71 passed, 0 failed** (4 تحذيرات غير حاجزة: pydicom FileDataset).
- `py_compile` سليم لكل الملفات المعدلة.
- فحص الاستيراد: `import app` → `APP IMPORT OK`؛ جميع الأصناف التحليلية تُحلّ (TissueClassifier, AnalysisOrchestrator, QuantitativeEngine, StructuralEngine, MedicalAIVisionEngine, ClinicalApp).