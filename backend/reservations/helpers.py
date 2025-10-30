from csv import DictReader, DictWriter
from datetime import datetime
import logging
import os
import random
import re
import sys

import dateparser
from django.core.mail import EmailMessage, get_connection
from django.utils.dateparse import parse_date
from smtp import SMTPServerDisconnected
import reservations.config as roombaht_config


logging.basicConfig(stream=sys.stdout,
                    level=roombaht_config.LOGLEVEL)

logger = logging.getLogger(__name__)


def real_date(a_date: str, year=None):
    """Convert string date into python date

    Args:
        a_date (str): date string,
            expected formats supported: "Mon - 11/7", "Mon 11/14", "11/7", "11/14/2024", "2024/11/14"
        year (Optional[int]): year, in 4-digit format
            Allows specification of year, otherwise is in current year at runtime
    Returns:
        date: python `date` object
    """
    if a_date is None:
        raise ValueError("a_date is None")

    a_date = str(a_date).strip()
    if a_date == '':
        raise ValueError("empty date string")

    # Strip out strings "Early" and "Late"
    a_date = re.sub(r'Early|Late', '', a_date, flags=re.IGNORECASE)

    year = year or datetime.now().year
    dateparser_settings = {
        'RETURN_AS_TIMEZONE_AWARE': True,
        # 'PREFER_DATES_FROM': '',
        'TIMEZONE': 'US/Pacific',
        'STRICT_PARSING': True,
    }

    parsed_datetime = dateparser.parse(
        a_date,
        languages=['en'],
        settings=dateparser_settings,
    )

    if parsed_datetime is None:
        parsed_datetime = dateparser.parse(
            f"{a_date} {year}",
            languages=['en'],
            settings=dateparser_settings,
        )
        if parsed_datetime is None:
            raise ValueError(f"Could not parse date: {a_date}")

    return parsed_datetime.date()


def take3_date(date_obj):
    """Converts date string "mm-dd-yyyy" to "day - mm/dd"

    Args:
        date_str (datetime.date): date string "mm-dd-yyyy"

    Returns:
        _type_: output format with abbreviated day of week
    """
    formatted_date = date_obj.strftime('%a - %m/%d')
    return formatted_date

def egest_csv(items, fields, filename):
    with open(filename, 'w') as output_handle:
        output_dict = DictWriter(output_handle, fieldnames=fields)
        output_dict.writeheader()
        for elem in items:
            output_dict.writerow(elem)

def ingest_csv(filename):
    # turns out DictReader will accept any iterable object
    csv_iter = None
    if isinstance(filename, str):
        if not os.path.exists(filename):
            raise Exception("input file %s not found" % filename)
        csv_iter = open(filename, "r")
    elif isinstance(filename, list):
        csv_iter = filename
    else:
        raise Exception('must pass filename or list to ingest_csv')

    input_dict = []
    input_items = []
    # filter out comments and blank lines
    input_dict = DictReader(filter(lambda row: len(row) > 0 and row[0]!='#', csv_iter), skipinitialspace=True)
    input_fields = [k.lstrip().rstrip() for k in input_dict.fieldnames if type(k)==str]
    for elem in input_dict:
        strip_elem = {k.lstrip().rstrip(): v.lstrip().rstrip() for k, v in elem.items() if type(k)==str and type(v)==str}
        input_items.append(strip_elem)

    return input_fields, input_items

def phrasing():
    words = None
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open("%s/../config/wordylyst.md" % dir_path , "r") as f:
        words = f.read().splitlines()
    word = words[random.randint(0, 999)].capitalize()+words[random.randint(0, 999)].capitalize()
    rand = random.randint(1,3)
    if(rand==1):
        word = word+str(random.randint(0,99))
    elif(rand==2):
        word = word+str(random.randint(0,99))+words[random.randint(0,999)].capitalize()
    else:
        word = word+words[random.randint(0,999)].capitalize()
    return word

def my_url():
    port = roombaht_config.URL_PORT
    if port not in ("80", "443"):
        port = ":%s" % port
    else:
        port = ''

    return "%s://%s%s" % (
        roombaht_config.URL_SCHEMA,
        roombaht_config.URL_HOST,
        port
    )

def ts_suffix():
    now = datetime.now()
    return now.strftime('%Y-%m-%d-%H-%M')


def send_email(addresses, subject, body, attachments=[]):
    if not roombaht_config.SEND_MAIL:
        logger.info("Would have sent email to %s, subject: %s", ','.join(addresses), subject)
        return

    real_addresses = []
    for address in addresses:
        if '@noop.com' not in address:
            # always send to normal emails
            real_addresses.append(address)
        else:
            if roombaht_config.DEV_MAIL != '':
                # if the ROOMBAHT_DEV_MAIL var is set then insert the address part
                #   of the @noop.com email address as a suffix and treat as normal
                email_address, _email_host = address.split('@')
                dev_address, dev_host = roombaht_config.DEV_MAIL.split('@')
                real_addresses.append(f"{dev_address}+{email_address}@{dev_host}")
            else:
                # otherwise just pretend to send the email
                logger.debug("Not really sending noop dot com email to %s, subject: %s",
                             address, subject)
                return

    msg = EmailMessage(subject=subject,
                       body=body,
                       to=real_addresses,
                       connection = get_connection())

    for attachment in attachments:
        if os.path.exists(attachment):
            msg.attach_file(attachment)
        else:
            logger.warning("attachment %s not found sending email to %s",
                           attachment, ','.join(addresses))

    logger.info("Sending email to %s, subject: %s", ','.join(real_addresses), subject)

    try:
        msg.send()
        return True
    except SMTPServerDisconnected:
        return False

