from typing import TypedDict

import config


class ProjectInfo(TypedDict):
    name: str
    project_dir: str
    collection_name: str | None


PROJECTS: dict[str, ProjectInfo] = {
    "business_web": {
        "name": "Business Web",
        "project_dir": config.BUSINESS_WEB_PROJECT_DIR,
        "collection_name": config.BUSINESS_WEB_COLLECTION_NAME,
    },
    "client_web": {
        "name": "Client Web",
        "project_dir": config.CLIENT_WEB_PROJECT_DIR,
        "collection_name": config.CLIENT_WEB_COLLECTION_NAME,
    },
    "jetlend_core": {
        "name": "Jetlend Core",
        "project_dir": config.JETLEND_CORE_PROJECT_DIR,
        "collection_name": config.JETLEND_CORE_COLLECTION_NAME,
    },
    "underwriter_web": {
        "name": "Underwriter Web",
        "project_dir": config.UNDERWRITER_WEB_PROJECT_DIR,
        "collection_name": config.UNDERWRITER_WEB_COLLECTION_NAME,
    },
    "jetlend_business_frontend": {
        "name": "Frontend Business",
        "project_dir": config.FRONTEND_BUSINESS_PROJECT_DIR,
        "collection_name": config.FRONTEND_BUSINESS_COLLECTION_NAME,
    },
    "jetlend_underwriting_frontend": {
        "name": "Frontend Underwriting",
        "project_dir": config.FRONTEND_BUSINESS_PROJECT_DIR,
        "collection_name": config.FRONTEND_BUSINESS_COLLECTION_NAME,
    },
    "jetlend_partner_frontend": {
        "name": "Frontend Partner",
        "project_dir": config.FRONTEND_PARTNER_PROJECT_DIR,
        "collection_name": config.FRONTEND_PARTNER_COLLECTION_NAME,
    },
    "jetlend_client_frontend": {
        "name": "Frontend Client",
        "project_dir": config.FRONTEND_CLIENT_PROJECT_DIR,
        "collection_name": config.FRONTEND_CLIENT_COLLECTION_NAME,
    },
    "jetlend_site_frontend": {
        "name": "Frontend Jetlend Site",
        "project_dir": config.FRONTEND_JETLEND_SITE_PROJECT_DIR,
        "collection_name": config.FRONTEND_JETLEND_SITE_COLLECTION_NAME,
    },
}
