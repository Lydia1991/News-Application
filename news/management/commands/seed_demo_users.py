"""
Management command: seed_demo_users

Creates one demo account for each role (Reader, Journalist, Editor) plus a
Django superuser so a mentor or reviewer can log in immediately.

Usage:
    python manage.py seed_demo_users

Re-running is safe; existing accounts are left unchanged.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from news.models import CustomUser, Publisher, Role
from news.utils import assign_role_group


DEMO_USERS = [
    {
        "username": "demo_editor",
        "email": "editor@breakingnews.dev",
        "password": "Editor@1234",
        "role": Role.EDITOR,
        "first_name": "Editorial",
        "last_name": "Team",
        "is_staff": True,
    },
    {
        "username": "demo_journalist",
        "email": "journalist@breakingnews.dev",
        "password": "Journalist@1234",
        "role": Role.JOURNALIST,
        "first_name": "Jane",
        "last_name": "Reporter",
        "is_staff": False,
    },
    {
        "username": "demo_reader",
        "email": "reader@breakingnews.dev",
        "password": "Reader@1234",
        "role": Role.READER,
        "first_name": "Sam",
        "last_name": "Reader",
        "is_staff": False,
    },
]

SUPERUSER = {
    "username": "admin",
    "email": "admin@breakingnews.dev",
    "password": "Admin@1234",
}


class Command(BaseCommand):
    help = "Seed one demo account per role plus a superuser for reviewer access."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset passwords of existing demo accounts to their defaults.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options["reset_passwords"]

        # ── Superuser ──────────────────────────────────────────────────────
        if not CustomUser.objects.filter(username=SUPERUSER["username"]).exists():
            CustomUser.objects.create_superuser(
                username=SUPERUSER["username"],
                email=SUPERUSER["email"],
                password=SUPERUSER["password"],
            )
            self.stdout.write(self.style.SUCCESS(
                f'  Created superuser  : {SUPERUSER["username"]}'
            ))
        else:
            if reset:
                su = CustomUser.objects.get(username=SUPERUSER["username"])
                su.set_password(SUPERUSER["password"])
                su.save(update_fields=["password"])
                self.stdout.write(f'  Reset password     : {SUPERUSER["username"]}')
            else:
                self.stdout.write(f'  Already exists     : {SUPERUSER["username"]}')

        # ── Role accounts ──────────────────────────────────────────────────
        for spec in DEMO_USERS:
            exists = CustomUser.objects.filter(username=spec["username"]).exists()
            if not exists:
                user = CustomUser.objects.create_user(
                    username=spec["username"],
                    email=spec["email"],
                    password=spec["password"],
                    role=spec["role"],
                    first_name=spec["first_name"],
                    last_name=spec["last_name"],
                    is_staff=spec["is_staff"],
                )
                assign_role_group(user)
                self.stdout.write(self.style.SUCCESS(
                    f'  Created {spec["role"]:<12}: {spec["username"]}'
                ))
            else:
                if reset:
                    user = CustomUser.objects.get(username=spec["username"])
                    user.set_password(spec["password"])
                    user.save(update_fields=["password"])
                    self.stdout.write(f'  Reset password     : {spec["username"]}')
                else:
                    self.stdout.write(f'  Already exists     : {spec["username"]}')

        # ── Demo publisher (so editor/journalist have something to work with) ─
        publisher, created = Publisher.objects.get_or_create(
            name="Breaking News Daily",
            defaults={"description": "The flagship demo publication."},
        )
        if created:
            editor = CustomUser.objects.filter(username="demo_editor").first()
            journalist = CustomUser.objects.filter(username="demo_journalist").first()
            if editor:
                publisher.editors.add(editor)
            if journalist:
                publisher.journalists.add(journalist)
            self.stdout.write(self.style.SUCCESS(
                "  Created publisher  : Breaking News Daily"
            ))

        # ── Summary table ─────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(
            "┌─────────────────────┬──────────────────────────────┬──────────────────┐"
        ))
        self.stdout.write(self.style.HTTP_INFO(
            "│ Role                │ Username                     │ Password         │"
        ))
        self.stdout.write(self.style.HTTP_INFO(
            "├─────────────────────┼──────────────────────────────┼──────────────────┤"
        ))
        rows = [
            ("Superuser (admin)",  SUPERUSER["username"],            SUPERUSER["password"]),
            ("Editor",             "demo_editor",                    "Editor@1234"),
            ("Journalist",         "demo_journalist",                "Journalist@1234"),
            ("Reader",             "demo_reader",                    "Reader@1234"),
        ]
        for role, uname, pwd in rows:
            self.stdout.write(self.style.HTTP_INFO(
                f"│ {role:<19} │ {uname:<28} │ {pwd:<16} │"
            ))
        self.stdout.write(self.style.HTTP_INFO(
            "└─────────────────────┴──────────────────────────────┴──────────────────┘"
        ))
        self.stdout.write("")
        self.stdout.write("Admin panel : http://127.0.0.1:8000/admin/")
        self.stdout.write("App home    : http://127.0.0.1:8000/")
        self.stdout.write("")
