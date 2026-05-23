from src.classifier import classify_file, role_to_destination


def test_school_classification():
    role, sensitivity, destination = classify_file("TTU transcript.pdf", "application/pdf")
    assert role == "School and Education"
    assert sensitivity == "School Record"
    assert destination == "02 School and Education"


def test_scouting_classification():
    role, sensitivity, destination = classify_file("BSA camp notes.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert role == "Scouting"
    assert destination == "04 Scouting"


def test_media_classification():
    role, sensitivity, destination = classify_file("summer_photo.JPG", "image/jpeg")
    assert role == "Photos and Media"
    assert destination == "08 Photos and Media"


def test_default_destination():
    assert role_to_destination("Review Later") == "99 Review Later"

