import sys
sys.path.insert(0, '/app')
from app.db import SessionLocal, list_account_database_ids, open_account_session, set_current_mailbox_id
from app.models.email import Email
from app.services.imap_folder_service import _list_folder_names, _ensure_folders_on_connection, _mailbox_cache_key
from app.services.imap_scanner import connect_imap
from app.services.mailbox_service import get_enabled_mailbox_configs

mid = [m for m in list_account_database_ids() if m != 'default'][0]
print('mailbox_id:', mid)

token = set_current_mailbox_id(mid)
db = open_account_session(mid)
try:
    email = db.query(Email).filter(Email.folder=='inbox').first()
    if not email:
        email = db.query(Email).first()
    print('email id:', email.id, 'uid:', email.imap_uid, 'folder:', email.folder)
    print('subject:', str(email.subject)[:60])
    msg_id = email.message_id
    imap_uid = email.imap_uid
finally:
    db.close()

mailboxes = get_enabled_mailbox_configs()
mailbox = mailboxes[0]
print('host:', mailbox.imap_host, 'user:', mailbox.imap_username)

conn = connect_imap(mailbox)
folders = _list_folder_names(conn)
print('Server folders:', folders)

cache_key = _mailbox_cache_key(mailbox)
state = _ensure_folders_on_connection(conn, mailbox, cache_key)
print('spam_folder:', state.spam_folder)
print('archive_folder:', state.archive_folder)
print('separator:', repr(state.separator))

status, data = conn.select('INBOX', readonly=False)
print('SELECT INBOX:', status, data)

if imap_uid:
    print('Testing COPY uid', imap_uid, 'to', state.spam_folder)
    cs, cd = conn.uid('copy', imap_uid, state.spam_folder)
    print('COPY result:', cs, cd)
else:
    print('No imap_uid stored - searching by Message-ID in INBOX')
    conn.select('INBOX', readonly=True)
    s, d = conn.uid('search', None, 'HEADER', 'Message-ID', msg_id)
    print('Search result:', s, d)

conn.logout()
print('DONE')
