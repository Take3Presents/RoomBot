import logging

logger = logging.getLogger(__name__)


class TransferChainService:
    @staticmethod
    def transfer_chain(ticket, guest_rows, depth=1):
        chain = []
        for row in guest_rows:
            if ticket == row.ticket_code:
                chain.append(row)
                if row.transferred_from_code != '':
                    a_chain = TransferChainService \
                        .transfer_chain(row.transferred_from_code,
                                        guest_rows,
                                        depth + 1)
                    if len(a_chain) == 0:
                        logger.debug("Unable to find recursive ticket for %s (depth %s)", ticket, depth)
                        return chain

                    chain += a_chain
                    logger.debug("Found transfer ticket %s source (depth %s)", ticket, depth)
                return chain
        return chain
