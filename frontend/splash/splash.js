const bar = document.getElementById("bar");
const logs = document.getElementById("logs");

const steps = [
    "Connecting secure channels...",
    "Loading camera streams...",
    "Starting behavior recognition engine...",
    "Calibrating threat scoring...",
    "Finalizing dashboard..."
];

let i = 0;
const interval = setInterval(()=>{
    logs.innerHTML += "> " + steps[i] + "<br>";
    bar.style.width = ((i+1)/steps.length)*100 + "%";
    i++;
    if(i === steps.length){
        clearInterval(interval);
    }
},800);

setTimeout(()=>{
    window.location.href="../auth/index.html";
},5200);
