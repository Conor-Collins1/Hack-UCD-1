"""Server-rendered pages. OWNER: Person 2."""
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / 'templates'))

@router.get('/', include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request=request, name='index.html')

@router.get('/leaderboard', include_in_schema=False)
def leaderboard(request: Request):
    return templates.TemplateResponse(request=request, name='leaderboard.html')

@router.get('/premium', include_in_schema=False)
def premium(request: Request):
    return templates.TemplateResponse(request=request, name='premium.html')

@router.get('/account', include_in_schema=False)
def account(request: Request):
    return templates.TemplateResponse(request=request, name='account.html')


@router.get('/feedback', include_in_schema=False)
def feedback_page(request: Request):
    return templates.TemplateResponse(request=request, name='feedback.html')
