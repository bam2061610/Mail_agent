from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_global_db
from app.schemas.system import (
    OperationStatusResponse,
    SetupCompleteRequest,
    SetupStatusResponse,
    SetupTestAiRequest,
    SetupTestMailboxRequest,
)
from app.services.settings_service import is_setup_completed
from app.services.setup_service import complete_setup, test_ai_configuration, test_mailbox_configuration

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
def get_setup_status(db: Session = Depends(get_global_db)) -> SetupStatusResponse:
    return SetupStatusResponse(completed=is_setup_completed(db))


@router.post("/test-ai", response_model=OperationStatusResponse)
def test_setup_ai(request: SetupTestAiRequest, db: Session = Depends(get_global_db)) -> OperationStatusResponse:
    if is_setup_completed(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup has already been completed")
    try:
        test_ai_configuration(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationStatusResponse()


@router.post("/test-mailbox", response_model=OperationStatusResponse)
def test_setup_mailbox(
    request: SetupTestMailboxRequest,
    db: Session = Depends(get_global_db),
) -> OperationStatusResponse:
    if is_setup_completed(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup has already been completed")
    try:
        test_mailbox_configuration(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationStatusResponse()


@router.post("/complete", response_model=OperationStatusResponse)
def complete_initial_setup(
    request: SetupCompleteRequest,
    db: Session = Depends(get_global_db),
) -> OperationStatusResponse:
    if is_setup_completed(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup has already been completed")
    try:
        complete_setup(db, request)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationStatusResponse()
