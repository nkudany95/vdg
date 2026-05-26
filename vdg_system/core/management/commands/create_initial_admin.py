"""
Creates the initial GlobalAdmin account.
Run once after setup: python manage.py create_initial_admin
"""
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Create the initial Global Admin account'

    def handle(self, *args, **options):
        from members.models import Member

        if Member.objects.filter(role='global_admin').exists():
            self.stdout.write(self.style.WARNING('A Global Admin already exists. Skipping.'))
            return

        next_id = Member.objects.get_next_user_id()
        admin = Member.objects.create_user(
            user_id=next_id,
            password='VDG@Admin2024!',
            email='admin@vdg.rw',
            first_name='VDG',
            last_name='Administrator',
            role='global_admin',
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Global Admin created!\n'
            f'  User ID : {admin.user_id}\n'
            f'  Email   : admin@vdg.rw\n'
            f'  Password: VDG@Admin2024!\n'
            f'  IMPORTANT: Change the password immediately after first login!'
        ))
