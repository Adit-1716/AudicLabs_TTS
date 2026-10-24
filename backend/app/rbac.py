from app.models import RoleName

PERMISSIONS = {
    "org.manage": {RoleName.SUPER_ADMIN, RoleName.ORG_ADMIN},
    "members.manage": {RoleName.SUPER_ADMIN, RoleName.ORG_ADMIN},
    "project.create": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
        RoleName.CLIENT,
    },
    "project.assign": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
    },
    "media.upload": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
        RoleName.TRANSCRIBER,
        RoleName.CLIENT,
    },
    "transcript.edit": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
        RoleName.TRANSCRIBER,
        RoleName.REVIEWER,
    },
    "transcript.review": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
        RoleName.REVIEWER,
    },
    "transcript.view": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
        RoleName.TRANSCRIBER,
        RoleName.REVIEWER,
        RoleName.CLIENT,
        RoleName.BILLING_MANAGER,
    },
    "billing.manage": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.BILLING_MANAGER,
    },
    "reports.view": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
        RoleName.BILLING_MANAGER,
    },
    "audit.view": {RoleName.SUPER_ADMIN, RoleName.ORG_ADMIN},
    "workflow.manage": {
        RoleName.SUPER_ADMIN,
        RoleName.ORG_ADMIN,
        RoleName.PROJECT_MANAGER,
    },
}


def can(role: RoleName | str | None, permission: str, is_super: bool = False) -> bool:
    if is_super:
        return True
    if role is None:
        return False
    if isinstance(role, str):
        role = RoleName(role)
    return role in PERMISSIONS.get(permission, set())


# Assessment mapping: Owner / Editor / Viewer
ASSESSMENT_ROLE = {
    RoleName.ORG_ADMIN: "Owner",
    RoleName.PROJECT_MANAGER: "Editor",
    RoleName.TRANSCRIBER: "Editor",
    RoleName.REVIEWER: "Editor",
    RoleName.BILLING_MANAGER: "Editor",
    RoleName.CLIENT: "Viewer",
    RoleName.SUPER_ADMIN: "Owner",
}
