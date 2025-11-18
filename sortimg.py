
import os
import shutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def sort_images_into_folders(image_dir, output_dir):
    """Sort images into separate folders based on the PDF file name."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for image_file in os.listdir(image_dir):
        if image_file.lower().endswith('.png'):
            # Extract the PDF name from the image file name
            pdf_name = '_'.join(image_file.split('_')[:-2])
            pdf_image_output_folder = os.path.join(output_dir, pdf_name)
            
            if not os.path.exists(pdf_image_output_folder):
                os.makedirs(pdf_image_output_folder)
            
            # Move the image file to the corresponding folder
            src_path = os.path.join(image_dir, image_file)
            dest_path = os.path.join(pdf_image_output_folder, image_file)
            shutil.move(src_path, dest_path)
            logging.info(f"Moved {src_path} to {dest_path}")

def main():
    """Main function to sort images into folders."""
    image_dir = 'ocr_images_old'  # Directory containing the unsorted images
    output_dir = 'ocr_images_sorted'  # Directory to save the sorted images
    
    try:
        sort_images_into_folders(image_dir, output_dir)
        logging.info("Image sorting completed.")
    except Exception as e:
        logging.error(f"An error occurred during image sorting: {e}")

if __name__ == "__main__":
    main()
