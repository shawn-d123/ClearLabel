
fetch("data.json")
    .then(response => response.json())
    .then(data => {
        for (const key in data) {
            const input = document.getElementById(key);

            if (input) {
                input.value = data[key];
            }
        }
    });



const submitData = document.getElementById('submit-btn');
/* This is temporary - eventually success will be run after data input */
submitData.addEventListener('click', success);

async function success() {
    document.getElementById("result").innerHTML = "<h2>Prescription ordered!</h2>";
}


