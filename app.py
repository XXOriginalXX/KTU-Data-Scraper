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
        
        # Step 1: Login to KTU portal
        login_url = "https://app.ktu.edu.in/login.htm"
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.content, 'html.parser')
        
        # Find the form and extract any hidden fields/tokens
        form = soup.find('form', {'name': 'loginform'})  # Adjust the form selector if needed
        if not form:
            debug_info['login_form'] = 'Form not found'
            form = soup.find('form')  # Try to find any form
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
        
        # Step 2: Navigate to student profile
        student_url = "https://app.ktu.edu.in/eu/stu/studentDetails.htm"
        profile_page = session.get(student_url)
        debug_info['profile_status'] = profile_page.status_code
        debug_info['profile_url_after'] = profile_page.url
        
        # Check if we're redirected back to login
        if "login" in profile_page.url.lower():
            return jsonify({"error": "Session expired or login failed", "debug": debug_info}), 401
        
        # Step 3: Get the full profile
        full_profile_url = "https://app.ktu.edu.in/eu/stu/viewFullProfile.htm"
        full_profile_page = session.get(full_profile_url)
        full_profile_soup = BeautifulSoup(full_profile_page.content, 'html.parser')
        debug_info['full_profile_status'] = full_profile_page.status_code
        debug_info['full_profile_url_after'] = full_profile_page.url
        
        # Step 4: Navigate to curriculum
        curriculum_url = "https://app.ktu.edu.in/eu/stu/curriculum.htm"
        curriculum_page = session.get(curriculum_url)
        curriculum_soup = BeautifulSoup(curriculum_page.content, 'html.parser')
        debug_info['curriculum_status'] = curriculum_page.status_code
        debug_info['curriculum_url_after'] = curriculum_page.url
        
        # Save part of the page content for debugging
        debug_info['curriculum_content'] = curriculum_page.text[:500]  # First 500 chars
        
        # Extract CGPA
        cgpa_element = curriculum_soup.find('div', string=lambda text: text and 'CGPA' in text)
        cgpa = "N/A"
        if cgpa_element:
            cgpa = cgpa_element.get_text().strip().split(':')[-1].strip()
            debug_info['cgpa_found'] = True
        else:
            debug_info['cgpa_found'] = False
            # Try alternative methods to find CGPA
            for div in curriculum_soup.find_all('div'):
                if 'CGPA' in div.get_text():
                    debug_info['possible_cgpa_div'] = div.get_text()
        
        # Step 5: Extract all semester results
        semester_results = {}
        
        # Find all semester links
        semester_links = curriculum_soup.find_all('a', href=lambda href: href and 'viewGradeCard.htm' in href)
        debug_info['semester_links_count'] = len(semester_links)
        
        if len(semester_links) == 0:
            # Try to find any links for troubleshooting
            all_links = curriculum_soup.find_all('a')
            debug_info['all_links_count'] = len(all_links)
            debug_info['all_links_sample'] = [link.get('href') for link in all_links[:5]]
        
        for link in semester_links:
            semester_name = link.get_text().strip()
            semester_url = "https://app.ktu.edu.in" + link['href']
            
            # Navigate to semester grade card
            grade_card_page = session.get(semester_url)
            grade_card_soup = BeautifulSoup(grade_card_page.content, 'html.parser')
            
            # Extract course results
            results_table = grade_card_soup.find('table', class_='ktu-table')
            if results_table:
                courses = []
                rows = results_table.find_all('tr')[1:]  # Skip header row
                
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        course = {
                            'code': cols[0].get_text().strip(),
                            'name': cols[1].get_text().strip(),
                            'credits': cols[2].get_text().strip(),
                            'grade': cols[3].get_text().strip(),
                            'result': cols[4].get_text().strip()
                        }
                        courses.append(course)
                
                # Extract semester SGPA
                sgpa_element = grade_card_soup.find('div', string=lambda text: text and 'SGPA' in text)
                sgpa = "N/A"
                if sgpa_element:
                    sgpa = sgpa_element.get_text().strip().split(':')[-1].strip()
                
                semester_results[semester_name] = {
                    'courses': courses,
                    'sgpa': sgpa
                }
            
            # Add a small delay to avoid overwhelming the server
            time.sleep(1)
        
        # Step 6: Extract student details
        student_details = {
            'name': 'N/A',
            'register_number': username,
            'branch': 'N/A',
            'batch': 'N/A'
        }
        
        details_table = full_profile_soup.find('table', class_='ktu-table')
        if details_table:
            debug_info['details_table_found'] = True
            rows = details_table.find_all('tr')
            debug_info['details_table_rows'] = len(rows)
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    label = cols[0].get_text().strip()
                    value = cols[1].get_text().strip()
                    
                    if 'Name' in label:
                        student_details['name'] = value
                    elif 'Branch' in label:
                        student_details['branch'] = value
                    elif 'Batch' in label:
                        student_details['batch'] = value
        else:
            debug_info['details_table_found'] = False
            # Try to find any tables for troubleshooting
            all_tables = full_profile_soup.find_all('table')
            debug_info['all_tables_count'] = len(all_tables)
            if len(all_tables) > 0:
                debug_info['first_table_classes'] = all_tables[0].get('class', 'No class')
        
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
