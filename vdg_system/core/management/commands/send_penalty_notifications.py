"""
Management command to send penalty reminder notifications.
Run: python manage.py send_penalty_notifications
Schedule with cron from the 25th of each month:
  0 8 25-31 * * cd /path/to/project && python manage.py send_penalty_notifications
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
import calendar

class Command(BaseCommand):
    help = 'Send payment reminder notifications to members who have not paid this month'

    def handle(self, *args, **options):
        from members.models import Member
        from payments.models import Payment, Notification

        today = date.today()
        # Only run from the 25th onward
        if today.day < 25:
            self.stdout.write(self.style.WARNING(
                f'Today is the {today.day}th. Notifications are sent from the 25th. Skipping.'
            ))
            return

        current_year = today.year
        current_month = today.month
        last_day = calendar.monthrange(current_year, current_month)[1]

        # Find members who haven't paid this month
        paid_member_ids = Payment.objects.filter(
            status='approved',
            payment_month__year=current_year,
            payment_month__month=current_month
        ).values_list('member_id', flat=True)

        unpaid_members = Member.objects.filter(
            role='member',
            is_active=True
        ).exclude(id__in=paid_member_ids)

        if not unpaid_members.exists():
            self.stdout.write(self.style.SUCCESS('All members have paid this month. No notifications needed.'))
            return

        # Get or find an admin to be the sender
        admin = Member.objects.filter(role__in=['admin', 'global_admin']).first()
        if not admin:
            self.stdout.write(self.style.ERROR('No admin found to create notification.'))
            return

        month_name = today.strftime('%B %Y')
        notif = Notification.objects.create(
            title=f'Payment Reminder — {month_name}',
            message=(
                f'This is a reminder that your monthly share contribution for {month_name} '
                f'is due by {last_day} {today.strftime("%B %Y")}. '
                f'Please submit your payment before the end of the month to avoid a 1,000 RWF penalty. '
                f'Log in to the VDG portal to upload your bordereau or make a direct payment.'
            ),
            category='payment',
            created_by=admin,
            send_to_all=False,
        )
        notif.recipients.set(unpaid_members)

        count = unpaid_members.count()
        self.stdout.write(self.style.SUCCESS(
            f'Successfully sent payment reminders to {count} member(s) who have not paid for {month_name}.'
        ))
