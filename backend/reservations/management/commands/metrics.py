"""Management command to display RoomBot metrics on the command line."""
from django.core.management.base import BaseCommand
from reservations.metrics import get_all_metrics


class Command(BaseCommand):
    """Display RoomBot metrics in text format."""

    help = "Display RoomBot system metrics"

    def handle(self, *args, **kwargs):
        """Execute the metrics command."""
        metrics = get_all_metrics()

        # Print header
        self.stdout.write(self.style.SUCCESS("\n=== RoomBot Metrics ===\n"))

        # Guest metrics
        self.stdout.write(self.style.HTTP_INFO("Guest Statistics:"))
        self.stdout.write(f"  Total guests:        {metrics['guest_count']}")
        self.stdout.write(f"  Unique emails:       {metrics['guest_unique']}")
        self.stdout.write(f"  Unplaced guests:     {metrics['guest_unplaced']}")

        # Room metrics
        self.stdout.write(self.style.HTTP_INFO("\nRoom Statistics:"))
        self.stdout.write(f"  Total rooms:         {metrics['rooms_count']}")
        self.stdout.write(f"  Occupied rooms:      {metrics['rooms_occupied']}")
        self.stdout.write(f"  Available rooms:     {metrics['rooms_available']}")
        self.stdout.write(f"  Percent placed:      {metrics['percent_placed']}%")
        self.stdout.write(f"  Swappable rooms:     {metrics['rooms_swappable']}")
        self.stdout.write(f"  Placed by roombot:   {metrics['rooms_placed_by_roombot']}")
        self.stdout.write(f"  Placed manually:     {metrics['rooms_placed_manually']}")

        # Swap metrics
        self.stdout.write(self.style.HTTP_INFO("\nSwap Statistics:"))
        self.stdout.write(f"  Rooms with swap codes: {metrics['rooms_swap_code_count']}")
        self.stdout.write(f"  Successful swaps:      {metrics['rooms_swap_success_count']}")

        # Onboarding metrics (per-email, deduplicated)
        self.stdout.write(self.style.HTTP_INFO("\nOnboarding Statistics (per email):"))
        self.stdout.write(f"  Onboarding sent:     {metrics['onboarding_sent_emails']}")
        self.stdout.write(f"  Onboarding pending:  {metrics['onboarding_pending_emails']}")
        self.stdout.write(f"  Can login:           {metrics['can_login_emails']}")
        self.stdout.write(f"  Users with rooms:    {metrics['users_with_rooms']}")
        self.stdout.write(f"  Known tickets:       {metrics['known_tickets']}")

        # Room type breakdown
        if metrics['rooms']:
            self.stdout.write(self.style.HTTP_INFO("\nRoom Type Breakdown:"))
            for room_info in metrics['rooms']:
                occupied = room_info['total'] - room_info['unoccupied']
                self.stdout.write(
                    f"  {room_info['room_type']:45} "
                    f"Total: {room_info['total']:3}  "
                    f"Occupied: {occupied:3}  "
                    f"Available: {room_info['unoccupied']:3}"
                )

        # Version
        self.stdout.write(self.style.HTTP_INFO(f"\nVersion: {metrics['version']}"))
        self.stdout.write("")  # blank line at end
