from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, StringConstraints

NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Phone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=8, max_length=30, pattern=r"^[0-9()+\-\s]+$"
    ),
]


class PatientCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "full_name": "Fernanda Ribeiro",
                    "email": "fernanda.ribeiro@example.com",
                    "phone": "(11) 97777-2002",
                }
            ]
        }
    )

    full_name: FullName
    email: NormalizedEmail
    phone: Phone


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    phone: str
