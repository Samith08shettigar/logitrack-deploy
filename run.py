from app import create_app

# Create application instance with default configurations
app = create_app('default')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
