from dukaanlens import create_app

app = create_app()

if __name__ == "__main__":
    # debug=False by default: the debugger allows code execution, so keep it off.
    # For local development set FLASK_DEBUG=1 and run `flask --app run run`.
    app.run(host="127.0.0.1", port=5000)
