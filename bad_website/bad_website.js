
let complete = false;


async function fetching() {
    fetch("data.json")
    .then(response => response.json())
    .then(data => {
        data.forEach(item => {
            const input = document.getElementById(item.name);
            if (input) {
                input.value = item.answer;
            }
        });
        complete = true;
    });
}




const submitData = document.getElementById('submit-btn');
/* This is temporary - eventually success will be run after data input */
submitData.addEventListener('click', success);

async function success() {
    document.getElementById("result").innerHTML = "<h2>Prescription ordered!</h2>";
}


