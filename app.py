import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, date, timedelta
from functools import wraps
import time

app = Flask(__name__)


app.secret_key = 'your_super_secret_key_here_FireHex' 



UID_TXT_FILE = '/root/FireHex/bypass_updated/uid.txt'
USER_JSON_FILE = os.path.join(os.path.dirname(__file__), 'user.json')
WHITELIST_IND_FILE = os.path.join(os.path.dirname(__file__), 'whitelist_ind.json')

SETTINGS_JSON_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')


ADMIN_USERNAME = 'firehex'
ADMIN_PASSWORD = 'firehex1' 


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



def load_users():
    if not os.path.exists(USER_JSON_FILE):
        return {}
    try:
        with open(USER_JSON_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def sync_whitelist_file(users_data):
    """Syncs active users to whitelist_ind.json in the format expected by the proxy/bot."""
    whitelist_data = {}
    today = datetime.now().date()
    
    for uid, data in users_data.items():
        try:
            # Check if user is expired
            if 'expiry_date' in data:
                expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
                if expiry_date >= today:
                    # Convert expiry date to Unix timestamp (end of that day 23:59:59)
                    # We create a datetime object for the end of the expiry day
                    expiry_dt = datetime.combine(expiry_date, datetime.max.time())
                    timestamp = int(expiry_dt.timestamp())
                    whitelist_data[str(uid)] = timestamp
        except (ValueError, KeyError):
            continue

    try:
        with open(WHITELIST_IND_FILE, 'w') as f:
            json.dump(whitelist_data, f, indent=4)
        print(f"Synced {len(whitelist_data)} users to {WHITELIST_IND_FILE}")
    except Exception as e:
        print(f"Error syncing whitelist file: {e}")

def save_users(users_data):
    with open(USER_JSON_FILE, 'w') as f:
        json.dump(users_data, f, indent=4)
    # Sync to whitelist_ind.json whenever users are saved
    sync_whitelist_file(users_data)

def remove_expired_users(users_data):
    today = datetime.now().date()
    uids_to_delete = []
    for uid, data in users_data.items():
        try:
            if 'expiry_date' not in data:
                 uids_to_delete.append(uid)
                 continue
            expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            if today > expiry_date:
                uids_to_delete.append(uid)
        except ValueError:
            uids_to_delete.append(uid)
    for uid in uids_to_delete:
        if uid in users_data:
            del users_data[uid]
    return users_data

def update_uid_txt(users_data):
    today = datetime.now().date()
    active_uids = []
    for uid, data in users_data.items():
        try:
            expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            if today <= expiry_date:
                active_uids.append(uid)
        except (ValueError, KeyError):
            pass 
    
    
    try:
        with open(UID_TXT_FILE, 'w') as f:
            if active_uids:
                f.write('\n'.join(active_uids) + '\n')
            else:
                f.write('')
    except Exception as e:
        
        
        print(f"WARNING: Could not update UID file at {UID_TXT_FILE}. Error: {e}")



def load_settings():
    """settings.json থেকে সেটিংস লোড করে, না থাকলে ডিফল্ট মান রিটার্ন করে।"""
    default_settings = {
        'cert_path': 'mitmproxy/mitmproxy-ca-cert.cer',
        'proxy_address': '46.247.108.191:30177'
    }
    if not os.path.exists(SETTINGS_JSON_FILE):
        return default_settings
    try:
        with open(SETTINGS_JSON_FILE, 'r') as f:
            settings = json.load(f)
            return {**default_settings, **settings}
    except json.JSONDecodeError:
        return default_settings

def save_settings(settings_data):
    with open(SETTINGS_JSON_FILE, 'w') as f:
        json.dump(settings_data, f, indent=4)

def read_certificate_file(cert_path):
    
    try:
        with open(cert_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"ERROR: Certificate file not found at path: {cert_path}"
    except PermissionError:
        return f"ERROR: Permission denied to read file: {cert_path}. Run Flask app as root or adjust permissions."
    except Exception as e:
        return f"ERROR: Could not read certificate file: {e}"




@app.before_request
def update_data_before_request():
    
    if request.path != url_for('login'):
        users = load_users()
        users = remove_expired_users(users)
        save_users(users)
        
        update_uid_txt(users) 

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('home'))
        return render_template('login.html', error='Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
   
    return render_template('admin_home.html') 

@app.route('/manage', methods=['GET', 'POST'])
@login_required
def manage_users():
    
    users = load_users()
    error = None
    success = None
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            user_id = request.form.get('user_id').strip()
            username = request.form.get('username').strip()
            expiry_date = request.form.get('expiry_date').strip()
            
            if user_id and username and expiry_date:
                try:
                    datetime.strptime(expiry_date, '%Y-%m-%d')
                    if user_id in users:
                        error = f"UID {user_id} already exists! Use Edit."
                    else:
                        users[user_id] = {
                            'username': username,
                            'expiry_date': expiry_date,
                            'added_on': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        save_users(users)
                        success = f"User {username} ({user_id}) added successfully!"
                except ValueError:
                    error = "Invalid Date Format. Please use YYYY-MM-DD."
                except Exception as e:
                    error = f"Error saving data: {e}"
            else:
                error = "Please fill all fields for adding a user."
        
        
        elif action == 'delete':
            uid_to_delete = request.form.get('uid_to_delete')
            if uid_to_delete in users:
                del users[uid_to_delete]
                save_users(users)
                success = f"UID {uid_to_delete} has been banned/deleted."
            else:
                error = f"UID {uid_to_delete} not found."
                
        
        elif action == 'edit_expiry':
            uid_to_edit = request.form.get('uid_to_edit')
            new_expiry_date = request.form.get('new_expiry_date')
            
            if uid_to_edit in users and new_expiry_date:
                try:
                    datetime.strptime(new_expiry_date, '%Y-%m-%d')
                    users[uid_to_edit]['expiry_date'] = new_expiry_date
                    save_users(users)
                    success = f"Expiry date for {uid_to_edit} updated to {new_expiry_date}."
                except ValueError:
                    error = "Invalid Date Format for editing."
            else:
                error = "Missing UID or new expiry date for editing."
                
        users = remove_expired_users(users)
        save_users(users)
        update_uid_txt(users)
        
        return redirect(url_for('manage_users', success=success, error=error))

    success = request.args.get('success')
    error = request.args.get('error')
    
    sorted_users = sorted(users.items(), key=lambda item: item[1].get('expiry_date', '9999-12-31'))
    
    return render_template('admin_manage.html', 
                           users=sorted_users, 
                           success=success, 
                           error=error,
                           today=date.today())

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    
    
    settings = load_settings()
    
    
    if request.method == 'POST':
        cert_path = request.form.get('cert_path').strip()
        proxy_address = request.form.get('proxy_address').strip()
        
        if cert_path and proxy_address:
            settings['cert_path'] = cert_path
            settings['proxy_address'] = proxy_address
            save_settings(settings)
            success = "Settings saved successfully!"
            error = None 
        else:
            error = "Both fields are required."
            success = None 
            
        return redirect(url_for('settings_page', success=success, error=error))
        
   
    success = request.args.get('success')
    error = request.args.get('error')
    certificate_code = read_certificate_file(settings['cert_path'])
        
    return render_template('admin_settings.html', 
                           settings=settings, 
                           success=success, 
                           error=error,
                           certificate_code=certificate_code)

@app.route('/api/get_whitelist', methods=['GET'])
def api_get_whitelist():
    try:
        if os.path.exists(WHITELIST_IND_FILE):
             with open(WHITELIST_IND_FILE, 'r') as f:
                data = json.load(f)
             return jsonify(data)
        else:
             return jsonify({})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('SERVER_PORT', 8989)) # Use assigned port or default to 8989
    print(f"Admin Panel running on http://0.0.0.0:{port}")
    # debug=False saves memory and disk space (no reloader)
    app.run(host='0.0.0.0', port=port, debug=False)