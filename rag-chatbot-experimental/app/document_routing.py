from __future__ import annotations


PROFILE_TO_PRIMARY_FILE = {
    "access_request": "procedure_acces.txt",
    "password_reset": "procedure_mot_de_passe.txt",
    "report_creation": "procedure_creation_rapport.txt",
    "support_help": "faq_support.txt",
    "usage_policy": "politique_utilisation.txt",
}

SUMMARY_FILES = [
    "procedure_acces.txt",
    "procedure_mot_de_passe.txt",
    "procedure_creation_rapport.txt",
    "faq_support.txt",
    "politique_utilisation.txt",
]


def expected_file_for_profile(routing_profile: str | None) -> str | None:
    if not routing_profile:
        return None
    return PROFILE_TO_PRIMARY_FILE.get(routing_profile)


def is_precise_document_profile(routing_profile: str | None) -> bool:
    return expected_file_for_profile(routing_profile) is not None
