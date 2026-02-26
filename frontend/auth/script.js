const API_BASE = "http://127.0.0.1:5000/api";

const form = document.querySelector(".login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const errorMessage = document.createElement('p'); // Create an error message element
errorMessage.style.color = '#e74c3c';
errorMessage.style.marginTop = '10px';
errorMessage.style.textAlign = 'center';
form.parentNode.insertBefore(errorMessage, form.nextSibling); // Insert it after the form

function togglePasswordVisibility() {
  const passwordField = document.getElementById("password");
  passwordField.type = passwordField.type === "password" ? "text" : "password";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorMessage.textContent = ''; // Clear previous errors

  const identifier = emailInput.value.trim();
  const password = passwordInput.value;

  if (!identifier || !password) {
    errorMessage.textContent = "Please fill all fields.";
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier: identifier, password: password })
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Login failed.");
    }

    // On successful login, save token and user info
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('user_name', data.user.fullname);


    // On successful login, check the role and redirect
    if (data.user && data.user.role === 'admin') {
        window.location.href = '../admin/admin.html';
    } else {
        // For non-admin users, redirect to a general dashboard
        window.location.href = '../dashboard/dashboard.html'; 
    }

  } catch (err) {
    errorMessage.textContent = err.message || "Server unavailable. Please try again later.";
    console.error("Login error:", err);
  }
});

// Attach togglePasswordVisibility to the span if it exists (assuming it's in the HTML)
const toggleSpan = document.querySelector('.toggle-password');
if (toggleSpan) {
    toggleSpan.addEventListener('click', togglePasswordVisibility);
}