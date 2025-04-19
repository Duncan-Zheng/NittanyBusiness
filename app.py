from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
import sqlite3
import csv
import hashlib
import re

# Initialize Flask application
app = Flask(__name__)
app.secret_key = 'nittany_business_secret_key'  # Change in production
app.config['DATABASE'] = 'database.db'
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

# Helper Function - Connect to Database
def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

# Start Database
def init_db():
    with open('schema.sql', 'r') as f:
        schema = f.read()

    conn = get_db_connection()
    conn.executescript(schema)
    conn.close()
    print("Database schema initialized.")

# Import Users from the given CSV file - uses SHA-256 hashing to encrypt passwords
def import_users_from_csv(csv_file):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if User table exist
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
    if cursor.fetchone() is None:
        print("Users table does not exist. Initialize the database first.")
        conn.close()
        return

    # Read users from CSV
    try:
        with open(csv_file, 'r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                # Hash the password before storing
                password_hash = hashlib.sha256(row['password'].encode('utf-8')).hexdigest()

                # Add a user into Table
                cursor.execute(
                    "INSERT OR REPLACE INTO Users (email, password) VALUES (?, ?)",
                    (row['email'], password_hash)
                )

                # Insert into respective sub class Table based on user type
                if 'helpdesk' in row['email']:
                    cursor.execute(
                        "INSERT OR REPLACE INTO Helpdesk (email, position) VALUES (?, ?)",
                        (row['email'], row.get('position', 'Support Staff'))
                    )
                elif 'buyer' in row['email']:
                    cursor.execute(
                        "INSERT OR REPLACE INTO Buyer (email, business_name, buyer_address_id) VALUES (?, ?, ?)",
                        (row['email'], row.get('business_name', 'Business'),
                         row.get('buyer_address_id', None))
                    )
                elif 'seller' in row['email']:
                    cursor.execute(
                        "INSERT OR REPLACE INTO Sellers (email, business_name, business_address_id, bank_routing_number, bank_account_number, balance) VALUES (?, ?, ?, ?, ?, ?)",
                        (row['email'], row.get('business_name', 'Business'), row.get('business_address_id', None),
                         row.get('bank_routing_number', None), row.get('bank_account_number', None), row.get('balance', 0))
                    )

        conn.commit()
        print("Users imported successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error importing users: {e}")
    finally:
        conn.close()

# Routes

# Index/Home Routing
@app.route('/')
def index():
    return render_template('index.html')

# Login routing
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        remember = 'remember' in request.form

        print(f"Login attempt for email: {email}")  # Debug print

        # Validate user credentials
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM Users WHERE email = ?', (email,)).fetchone()

        # Debug prints
        if user:
            print(f"User found in database: {user['email']}")
            # Show first part of hash
            print(f"Password hash in DB: {user['password'][:20]}...")
        else:
            print(f"No user found with email: {email}")
            conn.close()
            error = "Invalid email address."
            return render_template('login.html', error=error)

        # Calculate SHA-256 hash of the provided password for comparison
        provided_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        stored_hash = user['password']

        print(f"Comparing hashes:")
        print(f"Stored:   {stored_hash[:20]}...")
        print(f"Provided: {provided_hash[:20]}...")

        # Verify the password using direct comparison of SHA-256 hashes
        if provided_hash != stored_hash:
            conn.close()
            error = "Invalid password."
            print(f"Login failed: {error}")  # Debug print
            return render_template('login.html', error=error)

        # Login successful - store user info in session
        print(f"Login successful for {email}")  # Debug print
        session['user_email'] = email
        
        # Set a longer session lifetime if "remember me" is checked
        if remember:
            session.permanent = True

        # Determine user type based on database records
        buyer = conn.execute('SELECT * FROM Buyer WHERE email = ?', (email,)).fetchone()
        seller = conn.execute('SELECT * FROM Sellers WHERE email = ?', (email,)).fetchone()
        helpdesk = conn.execute('SELECT * FROM Helpdesk WHERE email = ?', (email,)).fetchone()
        conn.close()

        if helpdesk:
            session['user_type'] = 'helpdesk'
            print(f"Redirecting to helpdesk_dashboard")  # Debug print
            return redirect(url_for('helpdesk_dashboard'))
        elif buyer:
            session['user_type'] = 'buyer'
            print(f"Redirecting to buyer_dashboard")  # Debug print
            return redirect(url_for('buyer_dashboard'))
        elif seller:
            session['user_type'] = 'seller'
            print(f"Redirecting to seller_dashboard")  # Debug print
            return redirect(url_for('seller_dashboard'))
        else:
            session['user_type'] = 'user'
            print(f"Redirecting to dashboard")  # Debug print
            return redirect(url_for('dashboard'))

    # GET request - show login page
    return render_template('login.html', error=error)

# Signup Routing
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    print("Signup route accessed")  # Debug print
    
    if request.method == 'POST':
        try:
            print("Processing signup POST request")  # Debug print
            print(f"Form data: {request.form}")  # Debug print
            
            # Extract form data
            email = request.form['email']
            password = request.form['password']
            user_type = request.form['user_type']
            
            print(f"Signup attempt - Email: {email}, Type: {user_type}")  # Debug print
            
            # Check if email already exists
            conn = get_db_connection()
            existing_user = conn.execute('SELECT * FROM Users WHERE email = ?', (email,)).fetchone()
            
            if existing_user:
                print(f"Email {email} already exists in database")  # Debug print
                conn.close()
                error = "Email already registered. Please use a different email or login."
                return render_template('signup.html', error=error)
            
            # Hash the password using SHA-256 (for consistency with existing code)
            password_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            print(f"Password hashed: {password_hash[:20]}...")  # Debug print - only show part of hash
            
            # Insert the new user
            cursor = conn.cursor()
            cursor.execute('INSERT INTO Users (email, password) VALUES (?, ?)', (email, password_hash))
            print(f"User added to Users table: {email}")  # Debug print
            
            # Handle user-specific data based on type
            if user_type == 'buyer':
                business_name = request.form.get('business_name', '')
                
                # Handle address creation first
                street_num = request.form.get('street_num', '')
                street_name = request.form.get('street_name', '')
                zipcode = request.form.get('zipcode', '')
                
                # Check if zipcode exists, if not add it
                address_id = None
                if zipcode:
                    zip_exists = conn.execute('SELECT * FROM Zipcode_Info WHERE zipcode = ?', (zipcode,)).fetchone()
                    if not zip_exists:
                        city = request.form.get('city', '')
                        state = request.form.get('state', '')
                        print(f"Adding new zipcode: {zipcode}, {city}, {state}")  # Debug print
                        cursor.execute('INSERT INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', 
                                    (zipcode, city, state))
                
                # Create address record
                if street_num and street_name and zipcode:
                    print(f"Creating address record: {street_num} {street_name}, {zipcode}")  # Debug print
                    cursor.execute('''
                        INSERT INTO Address (zipcode, street_num, street_name) 
                        VALUES (?, ?, ?)
                    ''', (zipcode, street_num, street_name))
                    address_id = cursor.lastrowid
                    print(f"Created address with ID: {address_id}")  # Debug print
                
                # Create buyer record
                print(f"Creating buyer record: {email}, {business_name}, {address_id}")  # Debug print
                cursor.execute('''
                    INSERT INTO Buyer (email, business_name, buyer_address_id) 
                    VALUES (?, ?, ?)
                ''', (email, business_name, address_id))
                
                # Handle credit card info if provided
                card_num = request.form.get('credit_card_num', '')
                if card_num:
                    card_type = request.form.get('card_type', '')
                    expire_month = request.form.get('expire_month', '')
                    expire_year = request.form.get('expire_year', '')
                    security_code = request.form.get('security_code', '')
                    
                    print(f"Adding credit card for {email}")  # Debug print
                    cursor.execute('''
                        INSERT INTO Credit_Cards (credit_card_num, card_type, expire_month, 
                        expire_year, security_code, Owner_email) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (card_num, card_type, expire_month, expire_year, security_code, email))
                
            elif user_type == 'seller':
                business_name = request.form.get('seller_business_name', '')
                
                # Handle address creation first
                street_num = request.form.get('seller_street_num', '')
                street_name = request.form.get('seller_street_name', '')
                zipcode = request.form.get('seller_zipcode', '')
                
                # Check if zipcode exists, if not add it
                address_id = None
                if zipcode:
                    zip_exists = conn.execute('SELECT * FROM Zipcode_Info WHERE zipcode = ?', (zipcode,)).fetchone()
                    if not zip_exists:
                        city = request.form.get('seller_city', '')
                        state = request.form.get('seller_state', '')
                        print(f"Adding new zipcode: {zipcode}, {city}, {state}")  # Debug print
                        cursor.execute('INSERT INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', 
                                    (zipcode, city, state))
                
                # Create address record
                if street_num and street_name and zipcode:
                    print(f"Creating address record: {street_num} {street_name}, {zipcode}")  # Debug print
                    cursor.execute('''
                        INSERT INTO Address (zipcode, street_num, street_name) 
                        VALUES (?, ?, ?)
                    ''', (zipcode, street_num, street_name))
                    address_id = cursor.lastrowid
                    print(f"Created address with ID: {address_id}")  # Debug print
                
                # Get banking info
                bank_routing_number = request.form.get('bank_routing_number', '')
                bank_account_number = request.form.get('bank_account_number', '')
                
                # Create seller record with initial balance of 0
                print(f"Creating seller record: {email}, {business_name}, {address_id}")  # Debug print
                cursor.execute('''
                    INSERT INTO Sellers (email, business_name, business_address_id, 
                    bank_routing_number, bank_account_number, balance) 
                    VALUES (?, ?, ?, ?, ?, 0)
                ''', (email, business_name, address_id, bank_routing_number, bank_account_number))
                
            elif user_type == 'helpdesk':
                position = request.form.get('position', 'Support Staff')
                
                # Create helpdesk record
                print(f"Creating helpdesk record: {email}, {position}")  # Debug print
                cursor.execute('INSERT INTO Helpdesk (email, position) VALUES (?, ?)', 
                             (email, position))
            
            # Commit the transaction
            conn.commit()
            print(f"Successfully created account for {email} as {user_type}")  # Debug print
            conn.close()
            
            # Set session data
            session['user_email'] = email
            session['user_type'] = user_type
            
            print(f"Setting session for {email} as {user_type}")  # Debug print
            
            # Redirect to appropriate dashboard
            if user_type == 'buyer':
                return redirect(url_for('buyer_dashboard'))
            elif user_type == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif user_type == 'helpdesk':
                return redirect(url_for('helpdesk_dashboard'))
            else:
                return redirect(url_for('dashboard'))
                
        except Exception as e:
            print(f"Error during signup: {str(e)}")  # Debug print
            conn.rollback()
            conn.close()
            error = f"An error occurred during signup: {str(e)}"
            return render_template('signup.html', error=error)
    
    # For GET request, show the signup form
    # If a user type was specified in the query string, pre-select that option
    user_type = request.args.get('type', 'buyer')
    print(f"Showing signup form with preselected type: {user_type}")  # Debug print
    return render_template('signup.html', selected_type=user_type)

# Forgot Password Route
@app.route('/forgot-password')
def forgot_password():
    # This would typically email a reset link
    # For now, we'll just provide a placeholder page
    return render_template('forgot_password.html')

# Dashboard routing
@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', user_email=session['user_email'], user_type=session['user_type'])

# Dashboard routing for helpdesk
@app.route('/helpdesk_dashboard')
def helpdesk_dashboard():
    if 'user_email' not in session or session['user_type'] != 'helpdesk':
        return redirect(url_for('login'))
    return render_template('dashboard.html', user_email=session['user_email'], user_type='helpdesk')

# Buyer Dashboard routing
@app.route('/buyer_dashboard')
def buyer_dashboard():
    # Check if user is logged in and is a buyer
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    if session['user_type'] != 'buyer':
        return redirect(url_for('dashboard'))
    
    # Get the current user's information
    conn = get_db_connection()
    
    # Get buyer details
    buyer = conn.execute(
        'SELECT * FROM Buyer WHERE email = ?', 
        (session['user_email'],)
    ).fetchone()
    
    # Get buyer's address
    address = None
    if buyer and buyer['buyer_address_id']:
        address = conn.execute(
            '''SELECT a.*, z.city, z.state 
               FROM Address a 
               JOIN Zipcode_Info z ON a.zipcode = z.zipcode 
               WHERE a.address_id = ?''', 
            (buyer['buyer_address_id'],)
        ).fetchone()
    
    # Get buyer's payment methods
    payment_methods = conn.execute(
        'SELECT * FROM Credit_Cards WHERE Owner_email = ?',
        (session['user_email'],)
    ).fetchall()
    
    # Get order history
    orders = conn.execute(
        '''SELECT o.*, pl.Product_Title, pl.Product_Description, pl.Product_Price,
              (SELECT COUNT(*) FROM Reviews r WHERE r.Order_ID = o.Order_ID) > 0 AS has_review
           FROM Orders o
           JOIN Product_Listings pl ON o.Listing_ID = pl.Listing_ID
           WHERE o.Buyer_Email = ?
           ORDER BY o.Date DESC''',
        (session['user_email'],)
    ).fetchall()
    
    # Get all product categories
    categories = conn.execute(
        '''WITH RECURSIVE category_tree AS (
               SELECT category_name, parent_category, 0 AS level
               FROM Categories
               WHERE parent_category IS NULL
               UNION ALL
               SELECT c.category_name, c.parent_category, ct.level + 1
               FROM Categories c
               JOIN category_tree ct ON c.parent_category = ct.category_name
           )
           SELECT * FROM category_tree
           ORDER BY level, category_name'''
    ).fetchall()
    
    # Get featured products
    featured_products = conn.execute(
        '''SELECT pl.*, s.business_name AS seller_name,
              (SELECT AVG(r.Rate) FROM Reviews r 
               JOIN Orders o ON r.Order_ID = o.Order_ID
               WHERE o.Listing_ID = pl.Listing_ID) AS avg_rating,
              (SELECT COUNT(*) FROM Reviews r 
               JOIN Orders o ON r.Order_ID = o.Order_ID
               WHERE o.Listing_ID = pl.Listing_ID) AS review_count
           FROM Product_Listings pl
           JOIN Sellers s ON pl.Seller_Email = s.email
           WHERE pl.Status = 'active'
           ORDER BY avg_rating DESC, review_count DESC
           LIMIT 6'''
    ).fetchall()
    
    # Get recent products
    recent_products = conn.execute(
        '''SELECT pl.*, s.business_name AS seller_name,
              (SELECT AVG(r.Rate) FROM Reviews r 
               JOIN Orders o ON r.Order_ID = o.Order_ID
               WHERE o.Listing_ID = pl.Listing_ID) AS avg_rating,
              (SELECT COUNT(*) FROM Reviews r 
               JOIN Orders o ON r.Order_ID = o.Order_ID
               WHERE o.Listing_ID = pl.Listing_ID) AS review_count
           FROM Product_Listings pl
           JOIN Sellers s ON pl.Seller_Email = s.email
           WHERE pl.Status = 'active'
           ORDER BY pl.Listing_ID DESC
           LIMIT 6'''
    ).fetchall()
    
    conn.close()
    
    # Determine active tab from query parameter or default to 'products'
    active_tab = request.args.get('tab', 'products')
    
    return render_template(
        'buyer_dashboard.html',
        user_email=session['user_email'],
        user_type=session['user_type'],
        buyer=buyer,
        address=address,
        payment_methods=payment_methods,
        orders=orders,
        categories=categories,
        featured_products=featured_products,
        recent_products=recent_products,
        active_tab=active_tab
    )

# Product detail route
@app.route('/product/<int:listing_id>')
def product_detail(listing_id):
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get product details
    product = conn.execute(
        '''SELECT pl.*, s.business_name AS seller_name, s.email AS seller_email
           FROM Product_Listings pl
           JOIN Sellers s ON pl.Seller_Email = s.email
           WHERE pl.Listing_ID = ?''',
        (listing_id,)
    ).fetchone()
    
    if not product:
        conn.close()
        flash('Product not found')
        return redirect(url_for('buyer_dashboard'))
    
    # Get product reviews
    reviews = conn.execute(
        '''SELECT r.*, o.Buyer_Email
           FROM Reviews r
           JOIN Orders o ON r.Order_ID = o.Order_ID
           WHERE o.Listing_ID = ?
           ORDER BY o.Date DESC''',
        (listing_id,)
    ).fetchall()
    
    # Calculate average rating
    avg_rating = conn.execute(
        '''SELECT AVG(r.Rate) AS avg_rating, COUNT(*) AS review_count
           FROM Reviews r
           JOIN Orders o ON r.Order_ID = o.Order_ID
           WHERE o.Listing_ID = ?''',
        (listing_id,)
    ).fetchone()
    
    conn.close()
    
    return render_template(
        'product_detail.html',
        user_email=session['user_email'],
        user_type=session['user_type'],
        product=product,
        reviews=reviews,
        avg_rating=avg_rating
    )

# Product search route
@app.route('/product/search')
def product_search():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    # Get search parameters
    query = request.args.get('query', '')
    category = request.args.get('category', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    sort_by = request.args.get('sort_by', 'relevance')
    
    # Build search SQL query
    conn = get_db_connection()
    sql_query = '''
        SELECT pl.*, s.business_name AS seller_name,
            (SELECT AVG(r.Rate) FROM Reviews r 
             JOIN Orders o ON r.Order_ID = o.Order_ID
             WHERE o.Listing_ID = pl.Listing_ID) AS avg_rating,
            (SELECT COUNT(*) FROM Reviews r 
             JOIN Orders o ON r.Order_ID = o.Order_ID
             WHERE o.Listing_ID = pl.Listing_ID) AS review_count
        FROM Product_Listings pl
        JOIN Sellers s ON pl.Seller_Email = s.email
        WHERE pl.Status = 'active'
    '''
    
    params = []
    
    # Add keyword search
    if query:
        sql_query += ''' AND (
            pl.Product_Title LIKE ? OR 
            pl.Product_Description LIKE ? OR
            s.business_name LIKE ?
        )'''
        query_param = f'%{query}%'
        params.extend([query_param, query_param, query_param])
    
    # Add category filter
    if category:
        sql_query += ' AND pl.Category = ?'
        params.append(category)
    
    # Add price range filter
    if min_price and min_price.isdigit():
        sql_query += ' AND pl.Product_Price >= ?'
        params.append(float(min_price))
    
    if max_price and max_price.isdigit():
        sql_query += ' AND pl.Product_Price <= ?'
        params.append(float(max_price))
    
    # Add sorting
    if sort_by == 'price_low':
        sql_query += ' ORDER BY pl.Product_Price ASC'
    elif sort_by == 'price_high':
        sql_query += ' ORDER BY pl.Product_Price DESC'
    elif sort_by == 'rating':
        sql_query += ' ORDER BY avg_rating DESC, review_count DESC'
    elif sort_by == 'newest':
        sql_query += ' ORDER BY pl.Listing_ID DESC'
    else:  # Default to relevance
        if query:
            # For relevance, prioritize title matches, then description
            sql_query += ''' ORDER BY 
                CASE WHEN pl.Product_Title LIKE ? THEN 3
                     WHEN pl.Product_Description LIKE ? THEN 2
                     WHEN s.business_name LIKE ? THEN 1
                     ELSE 0
                END DESC'''
            query_param = f'%{query}%'
            params.extend([query_param, query_param, query_param])
        else:
            # If no query, order by rating
            sql_query += ' ORDER BY avg_rating DESC, review_count DESC'
    
    # Execute query
    products = conn.execute(sql_query, params).fetchall()
    
    # Get all categories for filtering
    categories = conn.execute(
        'SELECT category_name FROM Categories ORDER BY category_name'
    ).fetchall()
    
    conn.close()
    
    return render_template(
        'search_results.html',
        user_email=session['user_email'],
        user_type=session['user_type'],
        products=products,
        categories=categories,
        query=query,
        category=category,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        result_count=len(products)
    )

# Add route to submit reviews
@app.route('/submit_review', methods=['POST'])
def submit_review():
    if 'user_email' not in session or session['user_type'] != 'buyer':
        return redirect(url_for('login'))
    
    order_id = request.form.get('order_id')
    rating = request.form.get('rating')
    review_text = request.form.get('review_text')
    
    # Validate inputs
    if not order_id or not rating or not rating.isdigit():
        flash('Invalid review data')
        return redirect(url_for('buyer_dashboard', tab='orders'))
    
    # Check if order exists and belongs to the current user
    conn = get_db_connection()
    order = conn.execute(
        'SELECT * FROM Orders WHERE Order_ID = ? AND Buyer_Email = ?',
        (order_id, session['user_email'])
    ).fetchone()
    
    if not order:
        conn.close()
        flash('Order not found or not authorized')
        return redirect(url_for('buyer_dashboard', tab='orders'))
    
    # Check if review already exists
    existing_review = conn.execute(
        'SELECT * FROM Reviews WHERE Order_ID = ?',
        (order_id,)
    ).fetchone()
    
    if existing_review:
        # Update existing review
        conn.execute(
            'UPDATE Reviews SET Rate = ?, Review_Desc = ? WHERE Order_ID = ?',
            (rating, review_text, order_id)
        )
        flash('Your review has been updated!')
    else:
        # Create new review
        conn.execute(
            'INSERT INTO Reviews (Order_ID, Rate, Review_Desc) VALUES (?, ?, ?)',
            (order_id, rating, review_text)
        )
        flash('Thank you for your review!')
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('buyer_dashboard', tab='orders'))

# Add route for profile update
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    user_email = session['user_email']
    user_type = session['user_type']
    
    # Get form data
    if user_type == 'buyer':
        business_name = request.form.get('business_name', '')
        
        # Address info
        street_num = request.form.get('street_num', '')
        street_name = request.form.get('street_name', '')
        city = request.form.get('city', '')
        state = request.form.get('state', '')
        zipcode = request.form.get('zipcode', '')
        
        # Password change
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        conn = get_db_connection()
        
        # Update business name
        conn.execute(
            'UPDATE Buyer SET business_name = ? WHERE email = ?',
            (business_name, user_email)
        )
        
        # Handle address update
        if street_num and street_name and zipcode:
            # Check if zipcode exists
            zip_exists = conn.execute(
                'SELECT * FROM Zipcode_Info WHERE zipcode = ?', 
                (zipcode,)
            ).fetchone()
            
            if not zip_exists and city and state:
                conn.execute(
                    'INSERT INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)',
                    (zipcode, city, state)
                )
            
            # Get current address
            buyer = conn.execute(
                'SELECT * FROM Buyer WHERE email = ?', 
                (user_email,)
            ).fetchone()
            
            if buyer and buyer['buyer_address_id']:
                # Update existing address
                conn.execute(
                    'UPDATE Address SET zipcode = ?, street_num = ?, street_name = ? WHERE address_id = ?',
                    (zipcode, street_num, street_name, buyer['buyer_address_id'])
                )
            else:
                # Create new address
                conn.execute(
                    'INSERT INTO Address (zipcode, street_num, street_name) VALUES (?, ?, ?)',
                    (zipcode, street_num, street_name)
                )
                address_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                
                # Link address to buyer
                conn.execute(
                    'UPDATE Buyer SET buyer_address_id = ? WHERE email = ?',
                    (address_id, user_email)
                )
        
        # Handle password change
        if current_password and new_password and confirm_password:
            if new_password != confirm_password:
                conn.close()
                flash('New passwords do not match!')
                return redirect(url_for('buyer_dashboard', tab='profile'))
            
            # Verify current password
            user = conn.execute(
                'SELECT * FROM Users WHERE email = ?', 
                (user_email,)
            ).fetchone()
            
            current_hash = hashlib.sha256(current_password.encode('utf-8')).hexdigest()
            
            if user and user['password'] == current_hash:
                # Update password
                new_hash = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
                conn.execute(
                    'UPDATE Users SET password = ? WHERE email = ?',
                    (new_hash, user_email)
                )
                flash('Password updated successfully!')
            else:
                conn.close()
                flash('Current password is incorrect!')
                return redirect(url_for('buyer_dashboard', tab='profile'))
        
        conn.commit()
        conn.close()
        flash('Profile updated successfully!')
        return redirect(url_for('buyer_dashboard', tab='profile'))
    
    # Similar logic for other user types
    elif user_type == 'seller':
        # Handle seller profile update
        conn = get_db_connection()
        flash('Seller profile update functionality will be implemented soon.')
        conn.close()
        return redirect(url_for('seller_dashboard'))
    
    elif user_type == 'helpdesk':
        # Handle helpdesk profile update
        conn = get_db_connection()
        flash('Helpdesk profile update functionality will be implemented soon.')
        conn.close()
        return redirect(url_for('helpdesk_dashboard'))
    
    return redirect(url_for('dashboard'))

# Add route for payment method management
@app.route('/payment/add', methods=['GET', 'POST'])
def add_payment():
    if 'user_email' not in session or session['user_type'] != 'buyer':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Get payment details
        card_num = request.form.get('credit_card_num', '')
        card_type = request.form.get('card_type', '')
        expire_month = request.form.get('expire_month', '')
        expire_year = request.form.get('expire_year', '')
        security_code = request.form.get('security_code', '')
        
        # Validation
        if not card_num or not card_type or not expire_month or not expire_year or not security_code:
            flash('All payment fields are required')
            return render_template('add_payment.html', user_email=session['user_email'], user_type=session['user_type'])
        
        conn = get_db_connection()
        
        # Check if card already exists
        existing_card = conn.execute(
            'SELECT * FROM Credit_Cards WHERE credit_card_num = ?',
            (card_num,)
        ).fetchone()
        
        if existing_card:
            conn.close()
            flash('This card is already registered')
            return render_template('add_payment.html', user_email=session['user_email'], user_type=session['user_type'])
        
        # Add new card
        conn.execute(
            '''INSERT INTO Credit_Cards 
               (credit_card_num, card_type, expire_month, expire_year, security_code, Owner_email) 
               VALUES (?, ?, ?, ?, ?, ?)''',
            (card_num, card_type, expire_month, expire_year, security_code, session['user_email'])
        )
        
        conn.commit()
        conn.close()
        
        flash('Payment method added successfully!')
        return redirect(url_for('buyer_dashboard', tab='profile'))
    
    # GET request - show form
    return render_template('add_payment.html', user_email=session['user_email'], user_type=session['user_type'])

@app.route('/payment/<card_num>/edit', methods=['GET', 'POST'])
def edit_payment(card_num):
    if 'user_email' not in session or session['user_type'] != 'buyer':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Check if card exists and belongs to the user
    card = conn.execute(
        'SELECT * FROM Credit_Cards WHERE credit_card_num = ? AND Owner_email = ?',
        (card_num, session['user_email'])
    ).fetchone()
    
    if not card:
        conn.close()
        flash('Payment method not found')
        return redirect(url_for('buyer_dashboard', tab='profile'))
    
    if request.method == 'POST':
        # Get updated payment details
        card_type = request.form.get('card_type', '')
        expire_month = request.form.get('expire_month', '')
        expire_year = request.form.get('expire_year', '')
        security_code = request.form.get('security_code', '')
        
        # Validation
        if not card_type or not expire_month or not expire_year or not security_code:
            conn.close()
            flash('All payment fields are required')
            return render_template('edit_payment.html', card=card, user_email=session['user_email'], user_type=session['user_type'])
        
        # Update card
        conn.execute(
            '''UPDATE Credit_Cards 
               SET card_type = ?, expire_month = ?, expire_year = ?, security_code = ? 
               WHERE credit_card_num = ?''',
            (card_type, expire_month, expire_year, security_code, card_num)
        )
        
        conn.commit()
        conn.close()
        
        flash('Payment method updated successfully!')
        return redirect(url_for('buyer_dashboard', tab='profile'))
    
    # GET request - show form
    conn.close()
    return render_template('edit_payment.html', card=card, user_email=session['user_email'], user_type=session['user_type'])

@app.route('/payment/<card_num>/delete')
def delete_payment(card_num):
    if 'user_email' not in session or session['user_type'] != 'buyer':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Check if card exists and belongs to the user
    card = conn.execute(
        'SELECT * FROM Credit_Cards WHERE credit_card_num = ? AND Owner_email = ?',
        (card_num, session['user_email'])
    ).fetchone()
    
    if not card:
        conn.close()
        flash('Payment method not found')
        return redirect(url_for('buyer_dashboard', tab='profile'))
    
    # Delete the card
    conn.execute(
        'DELETE FROM Credit_Cards WHERE credit_card_num = ?',
        (card_num,)
    )
    
    conn.commit()
    conn.close()
    
    flash('Payment method deleted successfully!')
    return redirect(url_for('buyer_dashboard', tab='profile'))

# Order management routes
@app.route('/order/<int:order_id>')
def view_order(order_id):
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get order details
    order = None
    
    if session['user_type'] == 'buyer':
        order = conn.execute(
            '''SELECT o.*, pl.Product_Title, pl.Product_Description, pl.Product_Price,
                  s.business_name AS seller_name, s.email AS seller_email,
                  (SELECT COUNT(*) FROM Reviews r WHERE r.Order_ID = o.Order_ID) > 0 AS has_review
               FROM Orders o
               JOIN Product_Listings pl ON o.Listing_ID = pl.Listing_ID
               JOIN Sellers s ON pl.Seller_Email = s.email
               WHERE o.Order_ID = ? AND o.Buyer_Email = ?''',
            (order_id, session['user_email'])
        ).fetchone()
    elif session['user_type'] == 'seller':
        order = conn.execute(
            '''SELECT o.*, pl.Product_Title, pl.Product_Description, pl.Product_Price,
                  b.business_name AS buyer_name, b.email AS buyer_email,
                  (SELECT COUNT(*) FROM Reviews r WHERE r.Order_ID = o.Order_ID) > 0 AS has_review
               FROM Orders o
               JOIN Product_Listings pl ON o.Listing_ID = pl.Listing_ID
               JOIN Buyer b ON o.Buyer_Email = b.email
               WHERE o.Order_ID = ? AND pl.Seller_Email = ?''',
            (order_id, session['user_email'])
        ).fetchone()
    elif session['user_type'] == 'helpdesk':
        order = conn.execute(
            '''SELECT o.*, pl.Product_Title, pl.Product_Description, pl.Product_Price,
                  s.business_name AS seller_name, s.email AS seller_email,
                  b.business_name AS buyer_name, b.email AS buyer_email,
                  (SELECT COUNT(*) FROM Reviews r WHERE r.Order_ID = o.Order_ID) > 0 AS has_review
               FROM Orders o
               JOIN Product_Listings pl ON o.Listing_ID = pl.Listing_ID
               JOIN Sellers s ON pl.Seller_Email = s.email
               JOIN Buyer b ON o.Buyer_Email = b.email
               WHERE o.Order_ID = ?''',
            (order_id,)
        ).fetchone()
    
    if not order:
        conn.close()
        flash('Order not found or access denied')
        return redirect(url_for(f'{session["user_type"]}_dashboard'))
    
    # Get review if exists
    review = conn.execute(
        'SELECT * FROM Reviews WHERE Order_ID = ?',
        (order_id,)
    ).fetchone()
    
    conn.close()
    
    return render_template(
        'order_detail.html',
        user_email=session['user_email'],
        user_type=session['user_type'],
        order=order,
        review=review
    )

# Route for placing orders
@app.route('/order/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_email' not in session or session['user_type'] != 'buyer':
        return redirect(url_for('login'))
    
    listing_id = request.form.get('listing_id')
    
    if not listing_id:
        flash('Invalid product selection')
        return redirect(url_for('buyer_dashboard'))
    
    # For simplicity, we'll implement direct purchase rather than a cart system
    return redirect(url_for('checkout', listing_id=listing_id))

@app.route('/checkout/<int:listing_id>', methods=['GET', 'POST'])
def checkout(listing_id):
    if 'user_email' not in session or session['user_type'] != 'buyer':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # Get product details
    product = conn.execute(
        '''SELECT pl.*, s.business_name AS seller_name, s.email AS seller_email
           FROM Product_Listings pl
           JOIN Sellers s ON pl.Seller_Email = s.email
           WHERE pl.Listing_ID = ? AND pl.Status = 'active' ''',
        (listing_id,)
    ).fetchone()
    
    if not product:
        conn.close()
        flash('Product not available for purchase')
        return redirect(url_for('buyer_dashboard'))
    
    # Get payment methods
    payment_methods = conn.execute(
        'SELECT * FROM Credit_Cards WHERE Owner_email = ?',
        (session['user_email'],)
    ).fetchall()
    
    if request.method == 'POST':
        # Process the order
        quantity = request.form.get('quantity', '1')
        payment_method = request.form.get('payment_method')
        
        # Validation
        if not quantity.isdigit() or int(quantity) < 1 or int(quantity) > product['Quantity']:
            conn.close()
            flash('Invalid quantity')
            return render_template(
                'checkout.html',
                user_email=session['user_email'],
                user_type=session['user_type'],
                product=product,
                payment_methods=payment_methods
            )
        
        if not payment_method:
            conn.close()
            flash('Please select a payment method')
            return render_template(
                'checkout.html',
                user_email=session['user_email'],
                user_type=session['user_type'],
                product=product,
                payment_methods=payment_methods
            )
        
        # Create order
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO Orders (Seller_Email, Listing_ID, Buyer_Email, Date, Quantity, Payment)
               VALUES (?, ?, ?, date('now'), ?, ?)''',
            (product['Seller_Email'], listing_id, session['user_email'], quantity, 'completed')
        )
        
        order_id = cursor.lastrowid
        
        # Update product quantity
        new_quantity = product['Quantity'] - int(quantity)
        new_status = 'active' if new_quantity > 0 else 'sold'
        
        cursor.execute(
            'UPDATE Product_Listings SET Quantity = ?, Status = ? WHERE Listing_ID = ?',
            (new_quantity, new_status, listing_id)
        )
        
        # Update seller balance
        total_amount = product['Product_Price'] * int(quantity)
        cursor.execute(
            'UPDATE Sellers SET balance = balance + ? WHERE email = ?',
            (total_amount, product['Seller_Email'])
        )
        
        conn.commit()
        conn.close()
        
        flash('Order placed successfully!')
        return redirect(url_for('view_order', order_id=order_id))
    
    # GET request - show checkout form
    conn.close()
    return render_template(
        'checkout.html',
        user_email=session['user_email'],
        user_type=session['user_type'],
        product=product,
        payment_methods=payment_methods
    )

# Dashboard routing for seller
@app.route('/seller_dashboard')
def seller_dashboard():
    if 'user_email' not in session or session['user_type'] != 'seller':
        return redirect(url_for('login'))
    return render_template('dashboard.html', user_email=session['user_email'], user_type='seller')

# Logout routing
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)