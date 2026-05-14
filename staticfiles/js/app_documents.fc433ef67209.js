// Lịch sử duyệt chứng từ
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.history-button').forEach(button => {
    button.addEventListener('click', function() {
      const documentId = this.dataset.documentId; // Using dataset for consistency
      const url = this.dataset.url.replace('0', documentId);

      // Toggle the collapse programmatically
      const collapseElementId = `collapseExample-${documentId}`;
      const collapseElement = document.getElementById(collapseElementId);
      if (!new bootstrap.Collapse(collapseElement).toggle()) {
        // Initialize a new Bootstrap collapse instance and toggle it
        new bootstrap.Collapse(collapseElement, { toggle: true });
      }
      // Fetch the history data
      fetch(url, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          // 'X-CSRFToken': csrftoken, // Uncomment if you're making a POST request
        }
      })
      .then(response => {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.json();
      })
      .then(data => {
        const historyContainer = document.getElementById('history-container-' + documentId);
        historyContainer.innerHTML = ''; // Clear any existing content
        data.forEach(item => {
          const formattedDate = moment(item.trans_created_date).format('YYYY-MM-DD HH:mm:ss');
          historyContainer.innerHTML += `<p><em>User ${item.trans_created_by__username} duyệt ${item.checking_status_id__checking_status_name} at ${formattedDate}</em></p>`;
        });
      })
      .catch(error => console.error('Error:', error));
    });
  });
});

// Lịch sử nhận chứng từ
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.history-button-rei').forEach(button => {
    button.addEventListener('click', function() {
      const folderId = this.dataset.folderId; // Using dataset for consistency
      const url = this.dataset.url.replace('0', folderId);

      // Toggle the collapse programmatically
      const collapseElementId = `collapseExample-${folderId}`;
      const collapseElement = document.getElementById(collapseElementId);
      if (!new bootstrap.Collapse(collapseElement).toggle()) {
        // Initialize a new Bootstrap collapse instance and toggle it
        new bootstrap.Collapse(collapseElement, { toggle: true });
      }
      // Fetch the history data
      fetch(url, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          // 'X-CSRFToken': csrftoken, // Uncomment if you're making a POST request
        }
      })
      .then(response => {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.json();
      })
      .then(data => {
        const historyContainer = document.getElementById('history-container-x' + folderId);
        historyContainer.innerHTML = ''; // Clear any existing content
        data.forEach(item => {
          const formattedDate = moment(item.trans_created_date).format('YYYY-MM-DD HH:mm:ss');
          historyContainer.innerHTML += `<p><em>User ${item.trans_created_by__username} thao tác ${item.folder_status_id__folder_status_name} at ${formattedDate}</em></p>`;
        });
      })
      .catch(error => console.error('Error:', error));
    });
  });
});

// Navbar Adjustment
document.addEventListener("DOMContentLoaded", function(event) {
    adjustNavbar();
    // ... other DOMContentLoaded related code
  });
  window.onresize = adjustNavbar;
  function adjustNavbar() {
    var navbarHeight = document.getElementById('mynavbar').offsetHeight;
    document.body.style.paddingTop = navbarHeight + 'px';
  };

  // // Modal Adjustment of md_business_type
  // const myModal = document.getElementById('myModal')
  // const myInput = document.getElementById('myInput')
  
  // myModal.addEventListener('shown.bs.modal', () => {
  //   myInput.focus()
  // });



document.addEventListener('DOMContentLoaded', function() {
  setTimeout(function() {
      $(".alert").fadeOut('slow');
  }, 2000); // fades out after 2 seconds
});

  