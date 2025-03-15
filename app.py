import requests
from bs4 import BeautifulSoup
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/get-ktu-data', methods=['POST'])
def get_ktu_data():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    debug_info = {}  # Store debug information
    
    try:
        # Create a session with SSL verification disabled
        session = requests.Session()
        session.verify = False
        
        # Suppress only the specific InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Set user agent to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://app.ktu.edu.in/login.htm'
        }
        session.headers.update(headers)
        
        # Step 1: Load the login page to get any tokens
        login_url = "https://app.ktu.edu.in/login.htm"
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.content, 'html.parser')
        
        # Find the form and extract any hidden fields/tokens
        form = soup.find('form', {'name': 'loginform'})
        if not form:
            debug_info['login_form'] = 'Form not found'
            form = soup.find('form')
            if form:
                debug_info['alternative_form'] = form.get('action', 'No action attribute')
            return jsonify({"error": "Login form not found", "debug": debug_info}), 500
        
        # Extract all form inputs including hidden fields
        login_data = {
            'username': username,
            'password': password
        }
        
        for input_field in form.find_all('input'):
            if input_field.get('type') != 'submit' and input_field.get('name'):
                if input_field.get('name') not in ['username', 'password']:
                    login_data[input_field.get('name')] = input_field.get('value', '')
        
        # Get the correct form action URL
        form_action = form.get('action')
        if form_action:
            if form_action.startswith('/'):
                login_post_url = f"https://app.ktu.edu.in{form_action}"
            elif form_action.startswith('http'):
                login_post_url = form_action
            else:
                login_post_url = f"https://app.ktu.edu.in/{form_action}"
        else:
            login_post_url = login_url
        
        debug_info['login_post_url'] = login_post_url
        debug_info['login_data_keys'] = list(login_data.keys())
        
        # Submit login form
        login_response = session.post(login_post_url, data=login_data, allow_redirects=True)
        debug_info['login_status'] = login_response.status_code
        debug_info['login_url_after'] = login_response.url
        
        # Check if login was successful
        if "Invalid Username or Password" in login_response.text:
            return jsonify({"error": "Invalid username or password", "debug": debug_info}), 401
        
        # Check if we're still on the login page
        if "login" in login_response.url.lower():
            return jsonify({"error": "Login failed - still on login page", "debug": debug_info}), 401
        
        # Let's get the dashboard first to ensure we're properly logged in
        dashboard_url = login_response.url  # This should be the dashboard URL
        dashboard_page = session.get(dashboard_url)
        debug_info['dashboard_status'] = dashboard_page.status_code
        debug_info['dashboard_url'] = dashboard_url
        
        # Look for student specific links on the dashboard
        dashboard_soup = BeautifulSoup(dashboard_page.content, 'html.parser')
        student_links = dashboard_soup.find_all('a', href=True)
        debug_info['dashboard_links'] = [link['href'] for link in student_links[:10]]  # First 10 links for debugging
        
        # Try to get the grade page directly
        grade_page_url = "https://app.ktu.edu.in/eu/stu/grade.htm"
        grade_page = session.get(grade_page_url)
        grade_soup = BeautifulSoup(grade_page.content, 'html.parser')
        debug_info['grade_page_status'] = grade_page.status_code
        debug_info['grade_page_url'] = grade_page.url
        
        # Check if we're now on the grade page or redirected elsewhere
        if "grade.htm" not in grade_page.url:
            debug_info['grade_page_redirect'] = True
        
        # Try to find CGPA on the grade page
        cgpa = "N/A"
        cgpa_element = grade_soup.find('div', string=lambda text: text and 'CGPA' in text if text else False)
        if cgpa_element:
            cgpa = cgpa_element.get_text().strip().split(':')[-1].strip()
            debug_info['cgpa_found'] = True
        else:
            debug_info['cgpa_found'] = False
            # Try other methods to find CGPA
            for div in grade_soup.find_all('div'):
                text = div.get_text().strip()
                if text and 'CGPA' in text:
                    cgpa = text.split(':')[-1].strip()
                    debug_info['cgpa_found_alternative'] = True
                    break
        
        # Get semester results
        semester_results = {}
        
        # Find semester links from the grade page
        semester_links = grade_soup.find_all('a', href=lambda href: href and 'viewResult' in href if href else False)
        debug_info['semester_links_count'] = len(semester_links)
        
        if len(semester_links) == 0:
            # Try to find any links for troubleshooting
            all_links = grade_soup.find_all('a')
            debug_info['all_links_count'] = len(all_links)
            debug_info['all_links_sample'] = [link.get('href') for link in all_links[:5] if link.get('href')]
            
            # Look for any tables that might contain semester data
            result_tables = grade_soup.find_all('table')
            debug_info['result_tables_count'] = len(result_tables)
            
            # Try to find semester data in the page content
            semester_content = grade_soup.find('div', class_='col-md-12')
            if semester_content:
                debug_info['semester_content_found'] = True
                
                # Try to find tables in the content
                tables = semester_content.find_all('table')
                debug_info['content_tables_count'] = len(tables)
                
                # If we found tables, try to extract data from them
                if tables:
                    for i, table in enumerate(tables):
                        rows = table.find_all('tr')
                        semester_name = f"Semester {i+1}"
                        courses = []
                        
                        for row in rows[1:]:  # Skip header row
                            cols = row.find_all('td')
                            if len(cols) >= 5:
                                course = {
                                    'code': cols[0].get_text().strip() if cols[0].get_text() else 'N/A',
                                    'name': cols[1].get_text().strip() if cols[1].get_text() else 'N/A',
                                    'credits': cols[2].get_text().strip() if cols[2].get_text() else 'N/A',
                                    'grade': cols[3].get_text().strip() if cols[3].get_text() else 'N/A',
                                    'result': cols[4].get_text().strip() if cols[4].get_text() else 'N/A'
                                }
                                courses.append(course)
                        
                        if courses:
                            semester_results[semester_name] = {
                                'courses': courses,
                                'sgpa': 'N/A'  # We may not be able to extract SGPA
                            }
        
        # Attempt to get student details from the profile page
        profile_url = "https://app.ktu.edu.in/eu/stu/viewProfile.htm"
        profile_page = session.get(profile_url)
        profile_soup = BeautifulSoup(profile_page.content, 'html.parser')
        debug_info['profile_page_status'] = profile_page.status_code
        debug_info['profile_url_after'] = profile_page.url
        
        # Try to get student details from the profile page
        student_details = {
            'name': 'N/A',
            'register_number': username,
            'branch': 'N/A',
            'batch': 'N/A'
        }
        
        # Look for student details in any tables
        tables = profile_soup.find_all('table')
        debug_info['profile_tables_count'] = len(tables)
        
        if tables:
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        label = cols[0].get_text().strip() if cols[0].get_text() else ''
                        value = cols[1].get_text().strip() if cols[1].get_text() else ''
                        
                        if 'Name' in label:
                            student_details['name'] = value
                        elif 'Branch' in label:
                            student_details['branch'] = value
                        elif 'Batch' in label:
                            student_details['batch'] = value
        
        # If we couldn't get student details from tables, try other methods
        if student_details['name'] == 'N/A':
            # Look for any elements with potential student information
            for div in profile_soup.find_all('div'):
                text = div.get_text().strip()
                if text:
                    if 'Name:' in text:
                        student_details['name'] = text.split('Name:')[-1].strip().split('\n')[0]
                    elif 'Branch:' in text:
                        student_details['branch'] = text.split('Branch:')[-1].strip().split('\n')[0]
                    elif 'Batch:' in text:
                        student_details['batch'] = text.split('Batch:')[-1].strip().split('\n')[0]
        
        # Try to get name from the dashboard
        if student_details['name'] == 'N/A':
            user_name_element = dashboard_soup.find('div', class_='user-name')
            if user_name_element:
                student_details['name'] = user_name_element.get_text().strip()
        
        # Prepare the final response
        result = {
            'student_details': student_details,
            'cgpa': cgpa,
            'semester_results': semester_results,
            'debug_info': debug_info
        }
        
        return jsonify(result)
    
    except Exception as e:
        debug_info['exception'] = str(e)
        return jsonify({"error": str(e), "debug": debug_info}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
