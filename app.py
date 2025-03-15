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
    
    try:
        # Create a session with SSL verification disabled
        session = requests.Session()
        session.verify = False
        
        # Suppress only the specific InsecureRequestWarning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Step 1: Login to KTU portal
        login_url = "https://app.ktu.edu.in/login.htm"
        login_page = session.get(login_url)
        soup = BeautifulSoup(login_page.content, 'html.parser')
        
        # Find the form and extract any hidden fields/tokens if needed
        form = soup.find('form')
        if not form:
            return jsonify({"error": "Login form not found"}), 500
        
        # Prepare login data
        login_data = {
            'username': username,
            'password': password
        }
        
        # Submit login form
        login_response = session.post(login_url, data=login_data)
        
        # Check if login was successful
        if "Invalid Username or Password" in login_response.text:
            return jsonify({"error": "Invalid username or password"}), 401
        
        # Rest of your code remains the same...
        # Step 2: Navigate to student profile
        student_url = "https://app.ktu.edu.in/eu/stu/studentDetails.htm"
        profile_page = session.get(student_url)
        
        # Step 3: Get the full profile
        full_profile_url = "https://app.ktu.edu.in/eu/stu/viewFullProfile.htm"
        full_profile_page = session.get(full_profile_url)
        full_profile_soup = BeautifulSoup(full_profile_page.content, 'html.parser')
        
        # Step 4: Navigate to curriculum
        curriculum_url = "https://app.ktu.edu.in/eu/stu/curriculum.htm"
        curriculum_page = session.get(curriculum_url)
        curriculum_soup = BeautifulSoup(curriculum_page.content, 'html.parser')
        
        # Extract CGPA
        cgpa_element = curriculum_soup.find('div', string=lambda text: text and 'CGPA' in text)
        cgpa = "N/A"
        if cgpa_element:
            cgpa = cgpa_element.get_text().strip().split(':')[-1].strip()
        
        # Step 5: Extract all semester results
        semester_results = {}
        
        # Find all semester links
        semester_links = curriculum_soup.find_all('a', href=lambda href: href and 'viewGradeCard.htm' in href)
        
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
            rows = details_table.find_all('tr')
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
        
        # Prepare the final response
        result = {
            'student_details': student_details,
            'cgpa': cgpa,
            'semester_results': semester_results
        }
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
