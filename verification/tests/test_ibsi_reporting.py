from pathlib import Path
import re

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from core.ibsi_reporting import build_ibsi_ct_reporting_context


def _coverage():
    return {
        "morphology": {
            "ibsi_feature_definitions": 29,
            "computed_output_values": 29,
            "status": "computed",
            "reason": None,
        }
    }


def test_reporting_context_covers_all_guideline_items_without_overclaiming(tmp_path):
    image_path = tmp_path / "image.nii.gz"
    image_path.touch()
    report = build_ibsi_ct_reporting_context(
        configuration={
            "ibsi_configuration": "B",
            "resampling_mm": [2.0, 2.0, 1.0],
            "image_interpolation": "linear",
            "resampled_intensity_rounding": "nearest_integer",
            "mask_interpolation": "linear",
            "mask_threshold": 0.5,
            "resegmentation": {
                "method": "fixed_range",
                "range_lower_hu": -500.0,
                "range_upper_hu": 400.0,
            },
            "texture_and_histogram_discretization": {
                "method": "fixed bin number",
                "number_of_bins": 32,
            },
            "ivh_discretization": "direct",
            "texture_aggregation": ["AVER", "MERG"],
        },
        mask_source="NIfTI",
        roi_name=None,
        input_spacing_mm=[0.7, 0.7, 1.0],
        image_source_files=[image_path],
        feature_count=29,
        feature_family_coverage=_coverage(),
        application_version="1.0.2",
        radiomics_engine_version="26.9.0",
    )

    top_level_items = {
    re.match(r"\d+", item_id).group(0)
    for item_id in report["items"]
    }
    assert top_level_items == set(map(str, range(1, 77)))
    assert report["status"] == "incomplete"
    assert report["compliance_claim"] == "not_claimed"
    assert report["items"]["49"]["status"] == "reported"
    assert report["items"]["56c"]["status"] == "not_applicable"
    assert report["items"]["59"]["status"] == "not_claimed"
    assert sum(report["status_counts"].values()) == len(report["items"])
    assert report["dicom_metadata"]["status"] == "not_available"


def test_reporting_context_reads_allowlisted_dicom_tags_only(tmp_path):
    path = tmp_path / "ct.dcm"
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = generate_uid()
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.ImplementationClassUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.PatientName = "Sensitive^Patient"
    dataset.PatientID = "private-id"
    dataset.Modality = "CT"
    dataset.Manufacturer = "Example Scanner"
    dataset.KVP = 120
    dataset.save_as(path)

    report = build_ibsi_ct_reporting_context(
        configuration={},
        mask_source="DICOM RTSTRUCT",
        roi_name="Lung",
        input_spacing_mm=[0.7, 0.7, 1.0],
        image_source_files=[Path(path)],
        feature_count=0,
        feature_family_coverage=_coverage(),
        application_version="1.0.2",
        radiomics_engine_version="26.9.0",
    )

    dicom = report["dicom_metadata"]
    assert dicom["fields"]["Modality"]["values"] == ["CT"]
    assert dicom["fields"]["KVP"]["values"] == [120]
    assert "PatientName" not in dicom["fields"]
    assert "PatientID" not in dicom["fields"]
    assert "Sensitive^Patient" not in repr(dicom)
