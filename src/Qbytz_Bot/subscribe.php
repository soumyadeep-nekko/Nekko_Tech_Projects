<?php
if ($_SERVER["REQUEST_METHOD"] === "POST") {
    $email = filter_var($_POST['email'], FILTER_VALIDATE_EMAIL);

    if (!$email) {
        echo "Invalid email.";
        exit;
    }

    $file = 'subscribers.txt';

    // Save email if not already subscribed
    if (!file_exists($file) || strpos(file_get_contents($file), $email) === false) {
        file_put_contents($file, $email . PHP_EOL, FILE_APPEND);
    }

    // Send confirmation email
    $to = $email;
    $subject = "Thanks for Subscribing to Qbytz!";
    $message = "Hi,\n\nThank you for subscribing to Qbytz updates.\nWe'll keep you posted on services, training, and industry news.\n\n- Team Qbytz";
    $headers = "From: info@qbytz.com";

    if (mail($to, $subject, $message, $headers)) {
        echo "Subscribed successfully. Check your inbox.";
    } else {
        echo "Failed to send email.";
    }
}
?>
