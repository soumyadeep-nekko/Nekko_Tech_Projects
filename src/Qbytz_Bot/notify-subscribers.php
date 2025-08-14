<?php
// Only allow admin (add auth if needed)
$title = $_POST['title'] ?? 'Website Update';
$message = $_POST['message'] ?? 'Check out our latest updates on Qbytz.com!';
$file = 'subscribers.txt';

if (!file_exists($file)) {
    echo "No subscribers.";
    exit;
}

$emails = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

foreach ($emails as $email) {
    $to = $email;
    $subject = "Qbytz: $title";
    $headers = "From: info@qbytz.com";

    mail($to, $subject, $message, $headers);
}

echo "All subscribers notified.";
?>
