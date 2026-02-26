const API_BASE = "http://127.0.0.1:5000/api";

// ---------------- UTILITIES ----------------
function qs(id) {
  return document.getElementById(id);
}

function showAlert(msg, type = "error") {
  alert(msg); // keep simple, no UI redesign
}

function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ---------------- LOGIN ----------------
async function loginUser() {
  const identifier = qs("identifier")?.value.trim();
  const password = qs("password")?.value;

  if (!identifier || !password) {
    return showAlert("Please fill all fields");
  }

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, password })
    });

    const data = await res.json();

    if (!res.ok) {
      return showAlert(data.error || "Login failed");
    }

    sessionStorage.setItem("user_role", data.role);
    window.location.href = "../dashboard/dashboard.html";

  } catch {
    showAlert("Server not reachable");
  }
}

// ---------------- REGISTER (REQUEST ACCESS) ----------------
async function registerUser() {
  const fullname = document.getElementById("fullname").value.trim();
const email = document.getElementById("email").value.trim();
const organization = document.getElementById("organization").value.trim();


  if (!email || !username || !password) {
    return showAlert("All fields are required");
  }

  if (!validateEmail(email)) {
    return showAlert("Invalid email format");
  }

  if (password.length < 6) {
    return showAlert("Password must be at least 6 characters");
  }

  try {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, username, password })
    });

    const data = await res.json();

    if (!res.ok) {
      return showAlert(data.error || "Registration failed");
    }

    sessionStorage.setItem("pending_email", email);
    showAlert("OTP sent to email. Verify to continue.");
    window.location.href = "resend-otp.html";

  } catch {
    showAlert("Server error");
  }
}

// ---------------- VERIFY OTP ----------------
async function verifyOTP() {
  const otp = qs("otp")?.value.trim();
  const email = sessionStorage.getItem("pending_email");

  if (!email) {
    return showAlert("Session expired. Register again.");
  }

  if (!otp || otp.length !== 6) {
    return showAlert("Enter valid 6-digit OTP");
  }

  try {
    const res = await fetch(`${API_BASE}/auth/verify-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, otp })
    });

    const data = await res.json();

    if (!res.ok) {
      return showAlert(data.error || "OTP verification failed");
    }

    showAlert("Email verified. Await admin approval.");
    sessionStorage.removeItem("pending_email");
    window.location.href = "index.html";

  } catch {
    showAlert("Server error");
  }
}

// ---------------- FORGOT PASSWORD ----------------
async function forgotPassword() {
  const email = qs("email")?.value.trim();

  if (!email) {
    return showAlert("Email is required");
  }

  if (!validateEmail(email)) {
    return showAlert("Invalid email");
  }

  try {
    const res = await fetch(`${API_BASE}/auth/forgot-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email })
    });

    const data = await res.json();

    if (!res.ok) {
      return showAlert(data.error || "Email not registered");
    }

    sessionStorage.setItem("reset_email", email);
    showAlert("OTP sent to email");
    window.location.href = "resend-otp.html";

  } catch {
    showAlert("Server error");
  }
}

// ---------------- RESET PASSWORD ----------------
async function resetPassword() {
  const email = sessionStorage.getItem("reset_email");
  const otp = qs("otp")?.value.trim();
  const password = qs("password")?.value;

  if (!email) {
    return showAlert("Session expired");
  }

  if (!otp || !password) {
    return showAlert("All fields required");
  }

  if (password.length < 6) {
    return showAlert("Password too short");
  }

  try {
    const res = await fetch(`${API_BASE}/auth/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, otp, new_password: password })
    });

    const data = await res.json();

    if (!res.ok) {
      return showAlert(data.error || "Reset failed");
    }

    showAlert("Password updated. Login again.");
    sessionStorage.removeItem("reset_email");
    window.location.href = "index.html";

  } catch {
    showAlert("Server error");
  }
}
