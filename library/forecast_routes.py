"""Premium forecast API. Request/response shapes are in CLAUDE.md."""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from library import clock, db, forecast, status
from library.auth import current_user, require_user

router = APIRouter(prefix='/api')
logger = logging.getLogger(__name__)


def has_premium(user):
    if not user or not user['is_premium']:
        return False
    return user['premium_until'] is None or clock.as_utc(user['premium_until']) > clock.now()


@router.get('/forecast')
def get_forecast(request: Request, user_id: int = Depends(require_user)):
    with db.engine.connect() as conn:
        if not has_premium(current_user(conn, request)):
            return JSONResponse({'error': 'The 1-hour forecast is a Premium feature.', 'premium_required': True},
                                status_code=403)
        live = status.compute_status(conn)
    try:
        return forecast.get_forecast(live)
    except forecast.ForecastUnavailable as error:
        logger.error('Forecast unavailable: %s', error)
        return JSONResponse({'error': 'The forecast is temporarily unavailable. Please try again later.'},
                            status_code=503)
