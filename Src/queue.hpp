/****************************************************************/
/*                                                              */
/*  Copyright (C) 2018, M. Andelkovic, L. Covaci, A. Ferreira,  */
/*                    S. M. Joao, J. V. Lopes, T. G. Rappoport  */
/*                                                              */
/****************************************************************/

#include <algorithm>

std::string num2str3(int dir_num){
  std::string dir;
 
  switch(dir_num){
    case 0:
      dir = "xxx"; break;
    case 1:
      dir = "xxy"; break;
    case 2:
      dir = "xxz"; break;
    case 3:
      dir = "xyx"; break;
    case 4:
      dir = "xyy"; break;
    case 5:
      dir = "xyz"; break;
    case 6:
      dir = "xzx"; break;
    case 7:
      dir = "xzy"; break;
    case 8:
      dir = "xzz"; break;
    case 9:
      dir = "yxx"; break;
    case 10:
      dir = "yxy"; break;
    case 11:
      dir = "yxz"; break;
    case 12:
      dir = "yyx"; break;
    case 13:
      dir = "yyy"; break;
    case 14:
      dir = "yyz"; break;
    case 15:
      dir = "yzx"; break;
    case 16:
      dir = "yzy"; break;
    case 17:
      dir = "yzz"; break;
    case 18:
      dir = "zxx"; break;
    case 19:
      dir = "zxy"; break;
    case 20:
      dir = "zxz"; break;
    case 21:
      dir = "zyx"; break;
    case 22:
      dir = "zyy"; break;
    case 23:
      dir = "zyz"; break;
    case 24:
      dir = "zzx"; break;
    case 25:
      dir = "zzy"; break;
    case 26:
      dir = "zzz"; break;
    default:
      std::cout << "Invalid direction in num2str_dir3.\n"; exit(1);
  }
  return dir;
}

std::string num2str2(int dir_num){
  std::string dir;
 
  switch(dir_num){
    case 0:
      dir = "xx"; break;
    case 1:
      dir = "yy"; break;
    case 2:
      dir = "zz"; break;
    case 3:
      dir = "xy"; break;
    case 4:
      dir = "xz"; break;
    case 5:
      dir = "yx"; break;
    case 6:
      dir = "yx"; break;
    case 7:
      dir = "zx"; break;
    case 8:
      dir = "zy"; break;
    default:
      std::cout << "Invalid direction for the optical conductivity.\n"; exit(1);
  }
  return dir;
}


class measurement_queue{
  public:
    std::string direction_string;
    std::vector<int> NMoments;
    int NDisorder;
    int NRandom;
    std::string label;
    double time_length;
    measurement_queue(std::string dir_string, std::vector<int> moments, int disorder, int random, std::string name){
      direction_string = dir_string;
      NMoments = moments;
      NDisorder = disorder;
      NRandom = random;
      label = name;
    };


    void embed_time(double avg_duration){
      int prod = 1;
      for(unsigned int i = 0; i < NMoments.size(); i++)
        prod *= NMoments.at(i);

      time_length = prod*avg_duration*NDisorder*NRandom/MEMORY;
    };
};


std::vector<measurement_queue> fill_queue(char *name){
    H5::H5File * file = new H5::H5File(name, H5F_ACC_RDONLY);
    std::vector<measurement_queue> queue;

    // Now we must check which functions are asked by the configuration file.
    // Checking for the density of states
    H5::Exception::dontPrint();
    try{
      int NMoments, NRandom, NDisorder;
       debug_message("DOS: checking if we need to calculate DOS.\n");
       get_hdf5<int>(&NMoments,  file, (char *)   "/Calculation/dos/NumMoments");
       get_hdf5<int>(&NDisorder, file, (char *)   "/Calculation/dos/NumDisorder");
       //NDisorder = 1;
       get_hdf5<int>(&NRandom,   file, (char *)   "/Calculation/dos/NumRandoms");
       //dos = true;
       queue.push_back(measurement_queue("", {NMoments}, NDisorder, NRandom, "/Calculation/dos/MU"));
    } catch(H5::Exception& e) {debug_message("DOS: no need to calculate DOS.\n");}

    // Checking for the optical conductivity
    try{
      int direction, NMoments, NRandom, NDisorder;
       debug_message("Optical conductivity: checking if we need to calculate it.\n");
       get_hdf5<int>(&direction, file, (char *) "/Calculation/conductivity_optical/Direction");
       get_hdf5<int>(&NMoments, file, (char *)  "/Calculation/conductivity_optical/NumMoments");
       get_hdf5<int>(&NRandom, file, (char *)   "/Calculation/conductivity_optical/NumRandoms");
       get_hdf5<int>(&NDisorder, file, (char *)   "/Calculation/conductivity_optical/NumDisorder");
      
       // convert the numerical value for the direction into the string that represents it
       std::string dir(num2str2(direction));
       // same string, but separated by commas. This indicates a different gamma function
       std::string dirc = dir.substr(0,1)+","+dir.substr(1,2);
      
       queue.push_back(measurement_queue(dir,  {NMoments},           NDisorder, NRandom, "/Calculation/conductivity_optical/Lambda"+dir));
       queue.push_back(measurement_queue(dirc, {NMoments, NMoments}, NDisorder, NRandom, "/Calculation/conductivity_optical/Gamma" +dir));
    } catch(H5::Exception& e) {debug_message("Optical conductivity: no need to calculate it.\n");}


    // Checking for the dc conductivity
    try{
      int direction, NMoments, NRandom, NDisorder;
       debug_message("dc conductivity: checking if we need to calculate it.\n");
       get_hdf5<int>(&direction, file, (char *) "/Calculation/conductivity_dc/Direction");
       get_hdf5<int>(&NMoments, file, (char *)  "/Calculation/conductivity_dc/NumMoments");
       get_hdf5<int>(&NRandom, file, (char *)   "/Calculation/conductivity_dc/NumRandoms");
       get_hdf5<int>(&NDisorder, file, (char *) "/Calculation/conductivity_dc/NumDisorder");
       //conductivity_dc = true;

       // convert the numerical value for the direction into the string that represents it
       std::string dir(num2str2(direction));
       // same string, but separated by commas. This indicates a different gamma function
       std::string dirc = dir.substr(0,1)+","+dir.substr(1,2);
      
       queue.push_back(measurement_queue(dirc, {NMoments, NMoments}, NDisorder, NRandom, "/Calculation/conductivity_dc/Gamma"+dir));
    } catch(H5::Exception& e) {debug_message("dc conductivity: no need to calculate it.\n");}


    // nonlinear optical conductivity    
    try{
      int direction, NMoments, NRandom, NDisorder, special;
       debug_message("nonlinear optical cond: checking if we need to calculate it.\n");
       get_hdf5<int>(&direction, file, (char *)   "/Calculation/conductivity_optical_nonlinear/Direction");
       get_hdf5<int>(&NMoments, file, (char *)  "/Calculation/conductivity_optical_nonlinear/NumMoments");
       get_hdf5<int>(&NRandom, file, (char *)   "/Calculation/conductivity_optical_nonlinear/NumRandoms");
       get_hdf5<int>(&NDisorder, file, (char *)   "/Calculation/conductivity_optical_nonlinear/NumDisorder");
       get_hdf5<int>(&special, file, (char *)   "/Calculation/conductivity_optical_nonlinear/Special");
       //conductivity_optical_nonlinear = true;
       //NDisorder = 1;

       // convert the numerical value for the direction into the string that represents it
       std::string dir(num2str3(direction));                                                // xxx Gamma0
       std::string dirc1 = dir.substr(0,1) + "," + dir.substr(1,3);                         // x,xx Gamma1
       std::string dirc2 = dir.substr(0,2) + "," + dir.substr(2,3);                         // xx,x Gamma2
       std::string dirc3 = dir.substr(0,1) + "," + dir.substr(1,2) + "," + dir.substr(2,3); // x,x,x Gamma3

       std::string directory = "/Calculation/conductivity_optical_nonlinear/";
       
      // regular nonlinear calculation
      if(special != 1){
       queue.push_back(measurement_queue(dir,   {NMoments},                     NDisorder, NRandom, directory+"Gamma0"+dir));
       queue.push_back(measurement_queue(dirc1, {NMoments, NMoments},           NDisorder, NRandom, directory+"Gamma1"+dir));
       queue.push_back(measurement_queue(dirc2, {NMoments, NMoments},           NDisorder, NRandom, directory+"Gamma2"+dir));
       queue.push_back(measurement_queue(dirc3, {NMoments, NMoments, NMoments}, NDisorder, NRandom, directory+"Gamma3"+dir));
      }

      // special nonlinear calculation. In this case, it's going to be HBN, which is nonlinear
      // but only has simple objects that need calculating
      if(special == 1){
       queue.push_back(measurement_queue(dirc1, {NMoments, NMoments}, NDisorder, NRandom, directory+"Gamma1"+dir));
       queue.push_back(measurement_queue(dirc2, {NMoments, NMoments}, NDisorder, NRandom, directory+"Gamma2"+dir));
      }

    } catch(H5::Exception& e) {debug_message("nonlinear optical conductivity: no need to calculate it.\n");}

    delete file;
    

  return queue;

};




class singleshot_measurement_queue{
  public:
    std::string direction_string;
    int NDisorder;
    int NRandom;
    Eigen::Array<double, -1, 1> singleshot_energies;
    Eigen::Array<double, -1, 1> singleshot_gammas;
    Eigen::Array<double, -1, 1> singleshot_preserve_disorders;
    Eigen::Array<int, -1, 1> NMoments;
    Eigen::Array<double, -1, -1> singleshot_energiesgammas;
    std::string label;
    double time_length;

    void embed_time(double avg_duration){
      time_length = 0;
      for(int i = 0; i < NMoments.rows(); i++){
        time_length =+ NMoments(i)*avg_duration*2*NDisorder*NRandom;
      }
    };

    singleshot_measurement_queue(std::string dir_string, Eigen::Array<int, -1, 1> moments, int disorder, 
        int random, std::string name, Eigen::Array<double, -1, 1> energies, 
        Eigen::Array<double, -1, 1>  gammas, Eigen::Array<double, -1, 1> preserve_disorders){
      debug_message("Entered singleshot_measurement_queue constructor\n");
      direction_string = dir_string;
      NMoments = moments;
      NDisorder = disorder;
      NRandom = random;
      label = name;
      singleshot_energies = energies;
      singleshot_gammas = gammas;
      singleshot_preserve_disorders = preserve_disorders;

      // determine the number of rows in each of the quantities that characterize each job
      // and find out how many jobs there are (max_rows)
      long int rows[] = {NMoments.rows(), singleshot_energies.rows(), 
        singleshot_gammas.rows(), singleshot_preserve_disorders.rows()};
      int num_jobs = *std::max_element(rows, rows+4);
      
      // Check if the lists all have the same number of elements
      if(singleshot_preserve_disorders.rows() != num_jobs or
         singleshot_gammas.rows() != num_jobs or
         singleshot_energies.rows() != num_jobs or
         NMoments.rows() != num_jobs){
        std::cout << "Singleshot: The lists with gammas, energies, moments and preserve_disorder must"
          " all have the same number of elements. Exiting.\n";
        exit(1);
      }

      // Fill the array of jobs
      singleshot_energiesgammas = Eigen::Array<double, -1, -1>::Zero(num_jobs, 4);
      for(int i = 0; i < num_jobs; i++){
        singleshot_energiesgammas(i,0) = singleshot_energies(i);
        singleshot_energiesgammas(i,1) = singleshot_gammas(i);
        singleshot_energiesgammas(i,2) = singleshot_preserve_disorders(i);
        singleshot_energiesgammas(i,3) = NMoments(i);
      }

      debug_message("Left singleshot_measurement_queue constructor.\n");
    };

};

std::vector<singleshot_measurement_queue> fill_singleshot_queue(char *name){
    debug_message("Entered fill_singleshot_queue\n");
    H5::H5File * file = new H5::H5File(name, H5F_ACC_RDONLY);
    
    Eigen::Array<double, -1, 1> energies;
    Eigen::Array<double, -1, 1> gammas;
    Eigen::Array<double, -1, 1> preserve_disorders;
    Eigen::Array<int, -1, 1> moments;
    int NDisorder, NRandom, direction;
    std::string direction_string;
    
    NDisorder = 1;

    std::vector<singleshot_measurement_queue> queue;
    try{
       debug_message("single_shot dc checking if we need to calculate it.\n");
       get_hdf5<int>(&direction, file, (char *)   "/Calculation/singleshot_conductivity_dc/Direction");
       get_hdf5<int>(&NRandom, file, (char *)   "/Calculation/singleshot_conductivity_dc/NumRandoms");
       
       if(direction == 0)
         direction_string = "x,x";
       else if(direction == 1)
         direction_string = "y,y";
       else{
         std::cout << "Invalid singleshot direction. Exiting.\n";
         exit(1);
       }
       
      // We also need to determine the number of energies that we need to calculate
      H5::DataSet * dataset_energy     	= new H5::DataSet(file->openDataSet("/Calculation/singleshot_conductivity_dc/Energy"));
      H5::DataSpace * dataspace_energy 	= new H5::DataSpace(dataset_energy->getSpace());
      hsize_t dims_out[2];		
      dataspace_energy->getSimpleExtentDims(dims_out, NULL);	
      energies = Eigen::Array<double, -1, 1>::Zero(dims_out[0]*dims_out[1], 1);	
      delete dataspace_energy;
      delete dataset_energy;
      get_hdf5<double>(energies.data(),  	file, (char *)   "/Calculation/singleshot_conductivity_dc/Energy");
      
      // We also need to determine the number of gammas that we need to calculate
      H5::DataSet * dataset_gamma     	= new H5::DataSet(file->openDataSet("/Calculation/singleshot_conductivity_dc/Gamma"));
      H5::DataSpace * dataspace_gamma 	= new H5::DataSpace(dataset_gamma->getSpace());
      dataspace_gamma->getSimpleExtentDims(dims_out, NULL);	
      gammas = Eigen::Array<double, -1, 1>::Zero(dims_out[0]*dims_out[1], 1);	
      delete dataspace_gamma;
      delete dataset_gamma;
      get_hdf5<double>(gammas.data(),  	file, (char *)   "/Calculation/singleshot_conductivity_dc/Gamma");

      // We also need to determine the number of preserve disorders that we need to calculate
      H5::DataSet * dataset_preserve_disorder     	= new H5::DataSet(file->openDataSet("/Calculation/singleshot_conductivity_dc/PreserveDisorder"));
      H5::DataSpace * dataspace_preserve_disorder 	= new H5::DataSpace(dataset_preserve_disorder->getSpace());
      dataspace_preserve_disorder->getSimpleExtentDims(dims_out, NULL);	
      preserve_disorders = Eigen::Array<double, -1, 1>::Zero(dims_out[0]*dims_out[1], 1);	
      delete dataspace_preserve_disorder;
      delete dataset_preserve_disorder;
      get_hdf5<double>(preserve_disorders.data(),  	file, (char *)   "/Calculation/singleshot_conductivity_dc/PreserveDisorder");

      // We also need to determine the number of moments that we need to calculate
      H5::DataSet * dataset_moments     	= new H5::DataSet(file->openDataSet("/Calculation/singleshot_conductivity_dc/NumMoments"));
      H5::DataSpace * dataspace_moments 	= new H5::DataSpace(dataset_moments->getSpace());
      dataspace_moments->getSimpleExtentDims(dims_out, NULL);	
      moments = Eigen::Array<int, -1, 1>::Zero(dims_out[0]*dims_out[1], 1);	
      delete dataspace_moments;
      delete dataset_moments;
      get_hdf5<int>(moments.data(),  	file, (char *)   "/Calculation/singleshot_conductivity_dc/NumMoments");

      queue.push_back(singleshot_measurement_queue(direction_string, moments,
            NDisorder, NRandom, "/Calculation/singleshot_conductivity_dc/SingleShot",
            energies, gammas, preserve_disorders));
      
    } catch(H5::Exception& e) {debug_message("singleshot dc: no need to calculate it.\n");}

    delete file;
    
  return queue;
  debug_message("Left fill_singleshot_queue\n");
}

std::string print_time(double duration){
  if(duration < 500)
    return std::to_string(duration) + " seconds.";
  else if(duration >= 500 and duration < 60*3*60)
    return std::to_string(int(duration/60)) + " minutes.";
  else if(duration >= 60*60*3 and duration < 60*60*50)
    return std::to_string(int(duration/(60*60))) + " hours.";
  else
    return std::to_string(int(duration/(60*60*24))) + " days.";

}
