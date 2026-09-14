"""Compatibility exports for the single active Streamlit application path.

The application implementation lives in :mod:`app`; this module remains as a
stable import location for callers that used the former split UI module.
"""

from app import ClinicalApp
from utils.medical_ai_vision import MedicalAIVisionEngine

__all__ = ["ClinicalApp", "MedicalAIVisionEngine"]


if __name__ == "__main__":
    ClinicalApp().run()
