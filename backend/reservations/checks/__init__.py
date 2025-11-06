from fuzzywuzzy import fuzz
from reservations.models import Guest
import reservations.config as roombaht_config

def room_guest_name_mismatch(room):
    if not room.guest:
        return False

    for name in room.occupants():
        if fuzz.ratio(room.guest.name, name) >= roombaht_config.NAME_FUZZ_FACTOR:
            return False

    return True

def ticket_chain(p_guest):
    if not p_guest.transfer or p_guest.transfer == '':
        return [p_guest]

    # Use the model implementation to build the forward chain starting from
    # the ticket referenced by this guest's transfer. Guest.chain returns a
    # list ordered from the start ticket toward the tail, so reverse it to
    # match the previous ordering ([tail, ..., start]).
    forward_chain = Guest.chain(p_guest.transfer)
    combined = [p_guest] + forward_chain
    return list(reversed(combined))
