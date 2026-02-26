const role = sessionStorage.getItem("user_role");

if (location.pathname.includes("dashboard") && !role) {
  window.location.href = "../auth/index.html";
}
