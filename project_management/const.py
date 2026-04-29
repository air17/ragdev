from typing import TypedDict

import config


class ProjectInfo(TypedDict):
    name: str
    project_dir: str
    submodules: tuple[str, ...]
    project_prompt: str
    repo_url: str | None


BUSINESS_WEB_PROJECT_PROMPT = """This is a Django application called business-web, using MySQL db and Celery.
All the models (including for other repos) are located in jetlend_models submodule, most of the business-web models are in jetlend_models/business/models.py.
So if you need to find something about the most important models of this project, like Loan, Borrower, Partner or LoanRequest, they are located in that file, so you can filter your search.
Another important path is business_web/urls.py which contains most of borrower related APIs.
Partner logic is also part of this repo, with important files like partner_web/urls.py and jetlend_models/partner/models.py and models like Partner and PartnerBorrower, though use them only if the USER question is clearly about the partners.
There is also jl_main_project submodule with an old monolithic part of the project which is used by this repository (business-web) as well as by others not present here, like client-web and others.
link_to_gitlab_repo=https://gitlab.jetlend.ru/backend/business-web/-/blob/master
"""

CLIENT_WEB_PROJECT_PROMPT = """This is a Django application called client-web, using MySQL db and Celery.
All the models (including for other repos) are located in jetlend_models submodule, most of the client-web models are in jetlend_models/client/models.py.
Another important path is client_web/urls.py which contains most of client related APIs.
There is also jl_main_project submodule with an old monolithic part of the project which is used by this repository (client-web) as well as by others not present here, like business-web and others.
"""

JETLEND_CORE_PROJECT_PROMPT = """This is a Django application called jetlend-core, using MySQL db and Celery.
It is a core library and shared components for Jetlend platform, specifically loans, contracts and payments processing.
All the models (including for other repos) are located in jetlend_models submodule.
There is also jetlend_backend submodule with some shared logic used by other repos like business-web and client-web.
"""

UNDERWRITER_WEB_PROJECT_PROMPT = """This is a Django application called jetlend_underwriter_web, using MySQL db and Celery.
All the models (including for other repos) are located in jetlend_models submodule, most of the underwriter-web models are in jetlend_models/jetlend_underwriter/models.py (Underwriter, InterviewSlot, UnderwriterScoring, etc.) and jetlend_models/business/models.py (Loan, LoanRequest, BorrowerScoring, etc.).
Another important path is jetlend_underwriter_web/urls.py which contains most of underwriter admin panel related REST APIs.
There is also jl_main_project submodule with an old monolithic part of the project which is used by this repository (underwriter-web) as well as by others not present here, like business-web and others.
"""


PROJECTS: dict[str, ProjectInfo] = {
    "business_web": ProjectInfo(
        name="Business Web",
        project_dir=config.BUSINESS_WEB_PROJECT_DIR,
        submodules=("jl_main_project", "jetlend_models", "config-containers"),
        project_prompt=BUSINESS_WEB_PROJECT_PROMPT,
        repo_url="https://gitlab.jetlend.ru/backend/business-web/-/blob/master/",
    ),
    "client_web": ProjectInfo(
        name="Client Web",
        project_dir=config.CLIENT_WEB_PROJECT_DIR,
        submodules=("jl_main_project", "jetlend_models", "config-containers"),
        project_prompt=CLIENT_WEB_PROJECT_PROMPT,
        repo_url=None,
    ),
    "jetlend_core": ProjectInfo(
        name="Jetlend Core",
        project_dir=config.JETLEND_CORE_PROJECT_DIR,
        submodules=("jetlend_backend", "jetlend_models", "config-containers"),
        project_prompt=JETLEND_CORE_PROJECT_PROMPT,
        repo_url="https://gitlab.jetlend.ru/backend/jetlend-core/-/blob/master/",
    ),
    "underwriter_web": ProjectInfo(
        name="Underwriter Web",
        project_dir=config.UNDERWRITER_WEB_PROJECT_DIR,
        submodules=("jl_main_project", "jetlend_models", "config-containers"),
        project_prompt=UNDERWRITER_WEB_PROJECT_PROMPT,
        repo_url="https://gitlab.jetlend.ru/backend/jetlend_underwriter_web/-/blob/master/",
    ),
    "jetlend_business_frontend": ProjectInfo(
        name="Frontend Business",
        project_dir=config.FRONTEND_BUSINESS_PROJECT_DIR,
        submodules=("jetlend_react_lib",),
        project_prompt="React frontend for borrower crowdlending platform Jetlend",
        repo_url="https://gitlab.jetlend.ru/frontend/jetlend_business_frontend/-/blob/master/",
    ),
    "jetlend_underwriting_frontend": ProjectInfo(
        name="Frontend Underwriting",
        project_dir=config.FRONTEND_UNDERWRITING_PROJECT_DIR,
        submodules=("jetlend_react_lib",),
        project_prompt="React frontend for underwriter admin panel at crowdlending platform Jetlend used for borrower assessment and loan approval",
        repo_url="https://gitlab.jetlend.ru/frontend/jetlend_underwriting_frontend/-/blob/master/",
    ),
    "jetlend_partner_frontend": ProjectInfo(
        name="Frontend Partner",
        project_dir=config.FRONTEND_PARTNER_PROJECT_DIR,
        submodules=("jetlend_react_lib",),
        project_prompt="React frontend for partner portal at Jetlend crowdlending platform used by partners to register referred borrowers and track their status",
        repo_url="https://gitlab.jetlend.ru/frontend/jetlend_partner_frontend/-/blob/master/",
    ),
    "jetlend_client_frontend": ProjectInfo(
        name="Frontend Client",
        project_dir=config.FRONTEND_CLIENT_PROJECT_DIR,
        submodules=("jetlend_react_lib",),
        project_prompt="React frontend for investor portal at Jetlend crowdlending platform used by investors to browse and invest in loans",
        repo_url="https://gitlab.jetlend.ru/frontend/jetlend_client_frontend/-/blob/master/",
    ),
    "jetlend_site_frontend": ProjectInfo(
        name="Frontend Jetlend Site",
        project_dir=config.FRONTEND_JETLEND_SITE_PROJECT_DIR,
        submodules=("jetlend_react_lib",),
        project_prompt="React frontend for Jetlend crowdlending platform landing page and information website",
        repo_url="https://gitlab.jetlend.ru/frontend/jetlend_site_ssr/-/blob/master/",
    ),
}
