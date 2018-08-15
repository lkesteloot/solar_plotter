

import java.awt.Graphics2D;
import java.awt.Image;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.awt.image.RenderedImage;
import java.awt.image.WritableRaster;

import java.io.File;
import java.io.IOException;
import java.io.PrintWriter;

import javax.imageio.ImageIO;

/**
 * Converts a raster image to G codes for burning that image into wood
 * using the solar plotter.
 */
public class GCodes {
    public static void main(String[] args) throws Exception {
        new GCodes().run(args);
    }

    private void run(String[] args) throws Exception {
        if (args.length == 0) {
            System.err.println("Usage: GCodes in.png");
            System.exit(1);
        }

        // Parameters.

        // Origin in absolute coordinates, in inches.
        float originX = 0;
        float originY = 0;

        // Size in inches.
        float sizeX = 5;
        float sizeY = 5;

        // Number of pixels in drawn image.
        int columns = 32;
        int rows = 32;

        // Feed speed in inches per minute.
        float minFeed = 10;     // Black.
        float maxFeed = 30;     // White.

        // Number of colors to quantize to.
        int numShades = 8;

        // Process the image.
        BufferedImage original = ImageIO.read(new File(args[0]));

        // Keep track of the original ratio, in width-to-height.
        int originalWidth = original.getWidth();
        int originalHeight = original.getHeight();
        float ratio = (float) originalWidth / originalHeight;

        BufferedImage small = resize(original, columns, rows, true);
        quantize(small, numShades);

        generateGCodes(small, originX, originY, sizeX, sizeY, minFeed, maxFeed, numShades);

        BufferedImage largeAgain = resize(small, originalWidth, originalHeight, false);
        ImageIO.write(largeAgain, "jpg", new File("small.jpg"));
    }

    /**
     * Convert the image to black and white, normalize, and quantize down to numShades shades
     * of gray.
     */
    private void quantize(BufferedImage image, int numShades) {
        WritableRaster data = image.getRaster();
        int width = image.getWidth();
        int height = image.getHeight();

        double[] pixel = new double[3];

        // Convert to gray scale.
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                data.getPixel(x, y, pixel);
                double gray = 0.30*pixel[0] + 0.59*pixel[1] + 0.11*pixel[2];
                pixel[0] = gray;
                pixel[1] = gray;
                pixel[2] = gray;
                data.setPixel(x, y, pixel);
            }
        }

        // Normalize.
        double min = Double.MAX_VALUE;
        double max = -Double.MAX_VALUE;
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                data.getPixel(x, y, pixel);
                double gray = pixel[0];
                if (gray < min) {
                    min = gray;
                }
                if (gray > max) {
                    max = gray;
                }
            }
        }
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                data.getPixel(x, y, pixel);
                double gray = pixel[0];
                gray = (gray - min) / (max - min) * 255;
                pixel[0] = gray;
                pixel[1] = gray;
                pixel[2] = gray;
                data.setPixel(x, y, pixel);
            }
        }

        // Quantize.
        double mult = 256.0 / numShades;
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                data.getPixel(x, y, pixel);
                double gray = pixel[0];
                gray = (int) (gray / mult) * mult;
                pixel[0] = gray;
                pixel[1] = gray;
                pixel[2] = gray;
                data.setPixel(x, y, pixel);
            }
        }
    }

    private BufferedImage resize(BufferedImage input, int width, int height, boolean highQuality) {
        BufferedImage output = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = output.createGraphics();
        if (highQuality) {
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION,
                    RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.setRenderingHint(RenderingHints.KEY_RENDERING,
                    RenderingHints.VALUE_RENDER_QUALITY);
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                    RenderingHints.VALUE_ANTIALIAS_ON);
        }
        g.drawImage(input, 0, 0, width, height, null);
        g.dispose();

        return output;
    }

    private void generateGCodes(BufferedImage image, float originX, float originY,
            float sizeX, float sizeY, float minFeed, float maxFeed,
            int numShades) throws IOException {

        WritableRaster data = image.getRaster();
        int width = image.getWidth();
        int height = image.getHeight();

        double[] pixel = new double[3];

        PrintWriter out = new PrintWriter("out.g");
        out.println("G90"); // Absolute positioning.
        out.println("G20"); // Inches.
        out.println("G94"); // Feed per minute.
        out.println("G0 X" + originX + " Y" + originY); // Go to origin.

        double mult = 256.0 / numShades;
        int numMoves = 0;
        for (int y = 0; y < height; ++y) {
            int lastShade = -1;
            float Y = y * sizeY / (height - 1) + originY;

            for (int i = 0; i < width; ++i) {
                int x;
                if (y % 2 == 0) {
                    x = i;
                } else {
                    x = width - 1 - i;
                }

                float X = x * sizeX / (width - 1) + originX;

                data.getPixel(x, y, pixel);
                double gray = pixel[0];
                int shade = (int) (gray / mult);

                if (shade != lastShade || i == 0 || i == width - 1) {
                    // Inches per minute.
                    float normShade = (float) shade / (numShades - 1);
                    float feed = minFeed + normShade * (maxFeed - minFeed);

                    out.println("G1 X" + X + " Y" + Y + " F" + feed);
                    lastShade = shade;
                    ++numMoves;
                }
            }
        }

        out.close();

        int numPixels = width*height;
        System.out.println("Number of pixels: " + numPixels);
        System.out.println("Number of moves: " + numMoves);
        System.out.println("Pixels per move: " + ((float) numPixels / numMoves));
    }
}
