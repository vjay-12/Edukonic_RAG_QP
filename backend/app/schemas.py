from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

class ChapterWeight(BaseModel):
    chapter_no: int
    weight: float

class SectionConfig(BaseModel):
    id: str
    name: Optional[str] = None
    type: str  # mcq, assertion_reason, vsa, sa, la, case
    count: int
    marks: int

class PaperHeader(BaseModel):
    school_name: str = ""
    exam_name: str = ""
    date: str = ""
    duration: str = "1 Hour"
    instructions: List[str] = Field(default_factory=list)

class PaperConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    class_num: int = Field(default=10, alias="class")
    subject: str = "Science"
    total_marks: Optional[int] = None
    chapters: List[ChapterWeight]
    sections: List[SectionConfig]
    difficulty_mix: Dict[str, float] = Field(
        default_factory=lambda: {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    )
    competency_percent: int = 40
    avoid_duplicates_from_bank: bool = True
    header: Optional[PaperHeader] = None

    @model_validator(mode="after")
    def validate_config(self):
        # Validate chapter weights sum to ~1.0
        total_weight = sum(ch.weight for ch in self.chapters)
        if abs(total_weight - 1.0) > 0.05:
            raise ValueError(f"Chapter weights must sum to 1.0 (got {total_weight:.2f})")

        # Validate section marks
        calculated_marks = sum(sec.count * sec.marks for sec in self.sections)
        if self.total_marks is not None and self.total_marks != calculated_marks:
            raise ValueError(
                f"Config total_marks ({self.total_marks}) does not match sum of section marks ({calculated_marks})"
            )

        if not (0 <= self.competency_percent <= 100):
            raise ValueError("competency_percent must be between 0 and 100")

        return self

class SubQuestion(BaseModel):
    stem: str
    marks: int
    answer: str

class MarkingStep(BaseModel):
    step: str
    marks: float

class QuestionSource(BaseModel):
    chunk_ids: List[int] = Field(default_factory=list)
    pages: List[int] = Field(default_factory=list)

class QuestionContent(BaseModel):
    slot_no: int
    type: str  # mcq, assertion_reason, vsa, sa, la, case
    marks: int
    stem: str
    options: Optional[List[str]] = None
    correct_option: Optional[str] = None
    sub_questions: Optional[List[SubQuestion]] = None
    answer: str
    marking_scheme: Optional[List[MarkingStep]] = None
    difficulty: str = "medium"  # easy, medium, hard
    competency: bool = False
    bloom: str = "understand"  # remember, understand, apply, analyze, evaluate
    chapter_no: int
    topic: str
    source: QuestionSource = Field(default_factory=QuestionSource)
    insufficient_context: bool = False

class ValidationResult(BaseModel):
    grounded: bool = True
    answer_correct: bool = True
    marks_fit: bool = True
    single_correct_option: bool = True
    issues: List[str] = Field(default_factory=list)
    verdict: str = "pass"  # pass, warn, fail

class BlueprintReport(BaseModel):
    total_marks: int
    question_count: int
    marks_by_chapter: Dict[int, int]
    count_by_type: Dict[str, int]
    difficulty_split: Dict[str, int]
    competency_count: int
    competency_percent: float
    flagged_count: int

# API Schemas
class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    token: str
    authenticated: bool

class QuestionResponse(BaseModel):
    id: int
    slot_no: int
    section: str
    type: str
    marks: int
    chapter_no: int
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    competency: bool = False
    bloom: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    source_chunk_ids: Optional[List[int]] = None
    validation: Optional[Dict[str, Any]] = None
    status: str  # draft, accepted, rejected

class PaperDetailResponse(BaseModel):
    id: int
    title: str
    config: Dict[str, Any]
    status: str
    progress: int
    error: Optional[str] = None
    created_at: str
    questions: List[QuestionResponse] = Field(default_factory=list)
    blueprint_report: Optional[Dict[str, Any]] = None

class PaperListItem(BaseModel):
    id: int
    title: str
    total_marks: int
    question_count: int
    status: str
    progress: int
    created_at: str

class QuestionUpdateRequest(BaseModel):
    content: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

class QuestionRegenerateRequest(BaseModel):
    instruction: Optional[str] = None

class ChapterResponse(BaseModel):
    chapter_no: int
    chapter_title: str
    page_count: int
    chunks_count: int
    status: str

class BankItemResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    class_num: int = Field(alias="class")
    subject: str
    chapter_no: int
    type: str
    marks: int
    difficulty: Optional[str] = None
    competency: bool
    content: Dict[str, Any]
    approved_at: str

class FinalizeResponse(BaseModel):
    status: str
    paper_id: int
    saved_to_bank_count: int
    message: str
