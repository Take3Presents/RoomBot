from django.apps import AppConfig


class ReservationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reservations'
    verbose_name = 'Room Reservations'

    def ready(self):
        import reservations.checks.room
        import reservations.checks.user
        import reservations.checks.secret_party
